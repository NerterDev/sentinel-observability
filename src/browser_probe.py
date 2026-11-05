"""
Motor Playwright de Sonda Forense Sintética e Interceção Ativa
Plataforma de Observabilidade Web (Tier-S)
Caminho Canónico: src/browser_probe.py
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import uuid

from src.models import (
    CodeErrorDetail,
    ForensicIncident,
    LongTaskDetail,
    PerformanceMetrics,
    ProbeResult,
    SiteConfig,
    SlowRequestDetail,
    ThresholdsConfig,
)


CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
DEFAULT_LOCALE = "en-US"
DEFAULT_TIMEZONE = "America/New_York"

SENTINEL_INIT_SCRIPT = """
window.__sentinel_perf = {
  longTasks: [],
  unhandledErrors: []
};
try {
  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      window.__sentinel_perf.longTasks.push({
        duration: Math.round(entry.duration),
        startTime: Math.round(entry.startTime),
        name: entry.name || 'self',
        attribution: entry.attribution ? entry.attribution.map(a => a.name || a.containerSrc || '').join(', ') : ''
      });
    }
  });
  observer.observe({ entryTypes: ['longtask'] });
} catch(e) {}

window.addEventListener('unhandledrejection', (event) => {
  try {
    const reason = event.reason;
    window.__sentinel_perf.unhandledErrors.push({
      error_type: 'UnhandledPromiseRejection',
      message: reason ? (reason.message || String(reason)) : 'Promise rejeitada sem razão explícita',
      stack_trace: reason && reason.stack ? String(reason.stack) : null,
      timestamp: new Date().toISOString()
    });
  } catch(e) {}
});

window.addEventListener('error', (event) => {
  try {
    if (event.target && (event.target.tagName === 'SCRIPT' || event.target.tagName === 'LINK')) {
      const src = event.target.src || event.target.href || '';
      window.__sentinel_perf.unhandledErrors.push({
        error_type: 'ResourceLoadError',
        message: 'Falha ao carregar recurso externo: ' + src,
        source_file: src,
        timestamp: new Date().toISOString()
      });
    }
  } catch(e) {}
}, true);
"""


def parse_js_error(err_msg: str, stack: Optional[str]) -> Tuple[str, Optional[str], Optional[int], Optional[int]]:
    """
    Extrai tipo de erro, ficheiro de origem, linha e coluna de mensagens e stack traces JavaScript.
    """
    error_type = "JavaScriptError"
    if ":" in err_msg:
        potential_type = err_msg.split(":")[0].strip()
        if " " not in potential_type or "Uncaught " in potential_type:
            error_type = potential_type.replace("Uncaught ", "").strip()

    source_file = None
    line_number = None
    column_number = None

    if stack:
        pattern = r'(?:at\s+(?:[^\(]+?\s+\()?)?(https?://[^\s\)]+|[a-zA-Z0-9_\-\.\/]+\.js):(\d+):(\d+)\)?'
        matches = re.findall(pattern, stack)
        if matches:
            source_file = matches[0][0]
            try:
                line_number = int(matches[0][1])
                column_number = int(matches[0][2])
            except ValueError:
                pass

    return error_type, source_file, line_number, column_number


@dataclass
class ForensicBuffer:
    """Buffer acumulador em tempo real de eventos da consola, erros JS e rede."""
    js_errors: List[Dict[str, Any]] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    failed_ajax_calls: List[Dict[str, Any]] = field(default_factory=list)
    requests_log: List[Dict[str, Any]] = field(default_factory=list)
    long_tasks_fallback: List[Dict[str, Any]] = field(default_factory=list)

    def on_page_error(self, error: Any) -> None:
        """Captura exceções de execução JavaScript não tratadas."""
        err_msg = str(error)
        stack = getattr(error, "stack", None)
        error_type, source_file, line_no, col_no = parse_js_error(err_msg, str(stack) if stack else None)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": err_msg,
            "stack": str(stack) if stack else None,
            "error_type": error_type,
            "source_file": source_file,
            "line_number": line_no,
            "column_number": col_no,
        }
        self.js_errors.append(entry)

    def on_console_message(self, msg: Any) -> None:
        """Filtra mensagens de erro emitidas na consola do browser."""
        msg_type = getattr(msg, "type", "")
        if msg_type == "error":
            text = getattr(msg, "text", str(msg))
            self.console_errors.append(text)

    def on_response(self, response: Any, http_error_threshold: int = 400) -> None:
        """Inspeciona respostas HTTP e sinaliza falhas em wc-ajax e gateways."""
        status = getattr(response, "status", 200)
        url = getattr(response, "url", "")
        if status >= http_error_threshold or ("wc-ajax=" in url and status >= 400):
            req = getattr(response, "request", None)
            method = getattr(req, "method", "GET") if req else "GET"
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": url,
                "status": status,
                "method": method,
            }
            try:
                # Tenta obter uma prévia curta da resposta sem bloquear
                text_fn = getattr(response, "text", None)
                if callable(text_fn):
                    body = text_fn()
                    entry["body_preview"] = body[:500] if body else None
            except Exception:
                pass
            self.failed_ajax_calls.append(entry)

    def on_request_finished(self, request: Any) -> None:
        """Regista latência e metadados de cada recurso para análise de gargalos."""
        try:
            url = getattr(request, "url", "")
            method = getattr(request, "method", "GET")
            res_type = getattr(request, "resource_type", "other")
            duration_ms = 0.0
            timing_fn = getattr(request, "timing", None)
            if callable(timing_fn):
                t = timing_fn()
                if isinstance(t, dict):
                    duration_ms = max(0.0, float(t.get("responseEnd", 0.0)))

            response = None
            resp_fn = getattr(request, "response", None)
            if callable(resp_fn):
                response = resp_fn()

            status = getattr(response, "status", 200) if response else 200
            headers = getattr(response, "headers", {}) if response else {}
            content_type = headers.get("content-type", "")
            size_str = headers.get("content-length", "0")
            size_bytes = int(size_str) if str(size_str).isdigit() else 0
            cache_status = headers.get("cf-cache-status") or headers.get("x-cache")

            self.requests_log.append({
                "url": url,
                "method": method,
                "status": status,
                "duration_ms": round(duration_ms, 2),
                "resource_type": res_type,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "cache_status": cache_status,
            })
        except Exception:
            pass


def build_verdict_pt(
    failure_phase: str,
    buffer: ForensicBuffer,
    custom_reason: Optional[str] = None,
) -> str:
    """
    Classifica a causa-raiz técnica em português claro com base no buffer forense.
    """
    if custom_reason:
        return custom_reason

    if failure_phase == "shipping_check":
        return "Nenhum método de envio disponível para os EUA"

    if buffer.js_errors:
        first_err = buffer.js_errors[0].get("message", "Exceção não tratada")
        return f"Erro de JS impediu cálculo do checkout: {first_err[:120]}"

    for ajax in buffer.failed_ajax_calls:
        if "wc-ajax=" in ajax.get("url", ""):
            endpoint = ajax.get("url", "").split("wc-ajax=")[-1].split("&")[0]
            status = ajax.get("status", 500)
            return f"Falha assíncrona no endpoint WooCommerce (wc-ajax={endpoint}, HTTP {status})"

    if failure_phase == "payment_gateways":
        return "Recipientes de métodos de pagamento ausentes ou não renderizados"

    if failure_phase == "order_review":
        return "Timeout ao aguardar atualização da tabela de pedido (#order_review)"

    if failure_phase == "add_to_cart":
        return "Falha na reação da interface ao adicionar produto ao carrinho"

    if failure_phase == "product_page":
        return "Página do produto inacessível ou falha no carregamento inicial"

    if failure_phase == "checkout_navigation":
        return "Falha ao aceder à página de finalização de compra (checkout)"

    return f"Falha de execução na etapa: {failure_phase}"


class BrowserProbeEngine:
    """
    Motor sintético de sonda forense Playwright para lojas WooCommerce.
    """

    def __init__(self, screenshots_dir: Optional[Path] = None):
        self.screenshots_dir = screenshots_dir or Path("public/screenshots")

    def _ensure_screenshots_dir(self) -> Path:
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        return self.screenshots_dir

    def attach_forensic_listeners(
        self,
        page: Any,
        buffer: ForensicBuffer,
        http_error_threshold: int = 400,
    ) -> None:
        """Regista intercetores ativos de consola, exceções JS e tráfego de rede."""
        if hasattr(page, "on"):
            page.on("pageerror", buffer.on_page_error)
            page.on("console", buffer.on_console_message)
            page.on("response", lambda r: buffer.on_response(r, http_error_threshold))
            page.on("requestfinished", buffer.on_request_finished)

    def capture_evidence(
        self,
        page: Any,
        site_id: str,
        failure_phase: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Captura screenshot full-page e extrai trecho relevante do DOM no momento da quebra.
        """
        screenshot_path = None
        dom_extract = None
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_name = f"{site_id}_{failure_phase}_{now_str}.png"

        # 1. Screenshot
        try:
            out_dir = self._ensure_screenshots_dir()
            target_file = out_dir / file_name
            if hasattr(page, "screenshot"):
                page.screenshot(path=str(target_file), full_page=True)
                screenshot_path = f"public/screenshots/{file_name}"
        except Exception:
            pass

        # 2. Extrato DOM
        try:
            if hasattr(page, "content"):
                full_html = page.content()
                if isinstance(full_html, str):
                    # Extrai até 8000 caracteres para evidência leve
                    dom_extract = full_html[:8000]
        except Exception:
            pass

        return screenshot_path, dom_extract

    def extract_telemetry(
        self,
        page: Any,
        buffer: ForensicBuffer,
        current_phase: str,
    ) -> Tuple[List[CodeErrorDetail], List[LongTaskDetail], PerformanceMetrics, List[SlowRequestDetail]]:
        """Extrai métricas avançadas de desempenho, Core Web Vitals e erros estruturados."""
        perf_data: Dict[str, Any] = {}
        if hasattr(page, "evaluate"):
            try:
                perf_data = page.evaluate("""() => {
                    const perf = window.__sentinel_perf || { longTasks: [], unhandledErrors: [] };
                    const nav = performance.getEntriesByType('navigation')[0];
                    const paint = performance.getEntriesByType('paint') || [];
                    let fcp = null;
                    for (const p of paint) {
                        if (p.name === 'first-contentful-paint') fcp = Math.round(p.startTime);
                    }
                    return {
                        longTasks: perf.longTasks || [],
                        unhandledErrors: perf.unhandledErrors || [],
                        fcpMs: fcp,
                        domContentLoadedMs: nav ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : null,
                        loadEventMs: nav ? Math.round(nav.loadEventEnd - nav.startTime) : null,
                    };
                }""")
            except Exception:
                pass

        if not isinstance(perf_data, dict):
            perf_data = {}

        # 1. Erros estruturados de código
        structured_code_errors: List[CodeErrorDetail] = []
        for err in buffer.js_errors:
            structured_code_errors.append(
                CodeErrorDetail(
                    error_type=err.get("error_type", "JavaScriptError"),
                    message=err.get("message", "Exceção não tratada"),
                    source_file=err.get("source_file"),
                    line_number=err.get("line_number"),
                    column_number=err.get("column_number"),
                    stack_trace=err.get("stack"),
                    phase=err.get("phase", current_phase),
                )
            )
        for uerr in perf_data.get("unhandledErrors", []):
            structured_code_errors.append(
                CodeErrorDetail(
                    error_type=uerr.get("error_type", "UnhandledPromiseRejection"),
                    message=uerr.get("message", "Erro assíncrono não tratado"),
                    source_file=uerr.get("source_file"),
                    stack_trace=uerr.get("stack_trace"),
                    phase=current_phase,
                )
            )

        # 2. Tarefas longas (>50ms) e TBT
        long_task_details: List[LongTaskDetail] = []
        raw_tasks = perf_data.get("longTasks", []) + buffer.long_tasks_fallback
        for lt in raw_tasks:
            long_task_details.append(
                LongTaskDetail(
                    duration_ms=float(lt.get("duration", 0)),
                    start_time_ms=float(lt.get("startTime", 0)),
                    name=lt.get("name", "self"),
                    attribution=lt.get("attribution"),
                )
            )
        tbt = sum(max(0.0, lt.duration_ms - 50.0) for lt in long_task_details)

        # 3. Gargalos de rede (top 5 requisições lentas)
        all_requests = buffer.requests_log
        sorted_reqs = sorted(all_requests, key=lambda r: r.get("duration_ms", 0.0), reverse=True)
        slowest_requests = [
            SlowRequestDetail(
                url=r.get("url", ""),
                method=r.get("method", "GET"),
                status=r.get("status", 200),
                duration_ms=float(r.get("duration_ms", 0.0)),
                resource_type=r.get("resource_type", "xhr"),
                content_type=r.get("content_type"),
                size_bytes=r.get("size_bytes"),
                cache_status=r.get("cache_status"),
            )
            for r in sorted_reqs[:5]
        ]

        total_bytes = sum(r.get("size_bytes", 0) for r in all_requests)
        js_bytes = sum(r.get("size_bytes", 0) for r in all_requests if r.get("resource_type") == "script" or "javascript" in (r.get("content_type") or ""))
        css_bytes = sum(r.get("size_bytes", 0) for r in all_requests if r.get("resource_type") == "stylesheet" or "css" in (r.get("content_type") or ""))
        img_bytes = sum(r.get("size_bytes", 0) for r in all_requests if r.get("resource_type") == "image" or "image" in (r.get("content_type") or ""))
        font_bytes = sum(r.get("size_bytes", 0) for r in all_requests if r.get("resource_type") == "font" or "font" in (r.get("content_type") or ""))

        perf_metrics = PerformanceMetrics(
            total_blocking_time_ms=round(tbt, 2),
            long_tasks_count=len(long_task_details),
            fcp_ms=perf_data.get("fcpMs"),
            dom_content_loaded_ms=perf_data.get("domContentLoadedMs"),
            load_event_ms=perf_data.get("loadEventMs"),
            total_transferred_bytes=total_bytes,
            js_bytes=js_bytes,
            css_bytes=css_bytes,
            img_bytes=img_bytes,
            font_bytes=font_bytes,
            requests_count=len(all_requests),
        )

        return structured_code_errors, long_task_details, perf_metrics, slowest_requests

    def run_flow_on_page(
        self,
        page: Any,
        site: SiteConfig,
        thresholds: ThresholdsConfig,
        buffer: ForensicBuffer,
    ) -> ProbeResult:
        """
        Executa as 6 etapas do fluxo de checkout numa página ativa com intercetores.
        """
        step_latencies: Dict[str, float] = {}
        timeout_ms = thresholds.step_timeout_sec * 1000.0
        start_global = time.perf_counter()
        current_phase = "init"

        # Injeção de observadores de performance e erros antes de navegar
        if hasattr(page, "add_init_script"):
            try:
                page.add_init_script(SENTINEL_INIT_SCRIPT)
            except Exception:
                pass

        try:
            # =========================================================================
            # ETAPA 1: Página do Produto
            # =========================================================================
            current_phase = "product_page"
            t0 = time.perf_counter()
            page.goto(site.product_url, timeout=timeout_ms, wait_until="domcontentloaded")

            # Dispensa banner de cookies para evitar bloqueio de cliques
            try:
                cookie_btn = page.locator("#daextlwcn-cookie-notice-button-container button, .cookie-notice button, button:has-text('Accept all cookies'), button:has-text('Aceitar')").first
                if cookie_btn.count() > 0 and cookie_btn.is_visible():
                    cookie_btn.click(timeout=1000)
            except Exception:
                pass

            step_latencies["product_page"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 2: Adicionar ao Carrinho
            # =========================================================================
            current_phase = "add_to_cart"
            t0 = time.perf_counter()

            # Suporte a produtos variáveis: se existirem seletores de variação (.variations select), seleciona opção válida
            try:
                variation_selects = page.locator(".variations select, select[name^='attribute_']").all()
                for sel in variation_selects:
                    options = sel.locator("option").all()
                    for opt in options:
                        val = opt.get_attribute("value")
                        if val:
                            sel.select_option(val)
                            time.sleep(0.3)
                            break
            except Exception:
                pass

            # Localiza e clica no botão de adicionar ao carrinho
            page.wait_for_selector(site.selectors.add_to_cart_btn, timeout=timeout_ms)
            page.click(site.selectors.add_to_cart_btn)

            # Aguarda conclusão de eventuais requisições AJAX/POST decorrentes do clique
            try:
                page.wait_for_load_state("networkidle", timeout=3000.0)
            except Exception:
                pass

            # Aguarda feedback visual ou transição
            # Tenta encontrar a mensagem de sucesso ou mudança no carrinho
            try:
                page.wait_for_selector(site.selectors.cart_feedback, timeout=min(timeout_ms, 3000.0))
            except Exception:
                # Nem todas as lojas mostram .woocommerce-message; algumas redirecionam logo
                pass
            step_latencies["add_to_cart"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 3: Navegação para Checkout
            # =========================================================================
            current_phase = "checkout_navigation"
            t0 = time.perf_counter()
            checkout_full_url = site.selectors.checkout_url
            if not checkout_full_url.startswith("http://") and not checkout_full_url.startswith("https://"):
                checkout_full_url = urljoin(site.store_url, site.selectors.checkout_url)

            # Se a página atual ainda não for checkout, navega explicitamente
            current_url = getattr(page, "url", "")
            if "checkout" not in current_url and "finalizar" not in current_url:
                page.goto(checkout_full_url, timeout=timeout_ms, wait_until="domcontentloaded")

            # Resiliência para lojas que mantêm o utilizador no /cart/ antes do checkout
            post_nav_url = getattr(page, "url", "")
            if "cart" in post_nav_url and "checkout" not in post_nav_url:
                try:
                    proceed_btn = page.locator(".checkout-button, a[href*='checkout'], a[href*='finalizar']").first
                    if proceed_btn.count() > 0 and proceed_btn.is_visible():
                        proceed_btn.click()
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            step_latencies["checkout_navigation"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 4: Montagem da Tabela de Revisão (#order_review)
            # =========================================================================
            current_phase = "order_review"
            t0 = time.perf_counter()
            page.wait_for_selector(site.selectors.order_review_table, timeout=timeout_ms)
            # Se houver bloqueio AJAX ativo (blockOverlay), aguarda liberação
            try:
                page.wait_for_selector(".blockUI.blockOverlay", state="detached", timeout=5000.0)
            except Exception:
                pass
            step_latencies["order_review"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 5: Verificação de Frete Bloqueado (.woocommerce-no-shipping-available-html)
            # =========================================================================
            current_phase = "shipping_check"
            t0 = time.perf_counter()
            shipping_blocked_el = None
            if hasattr(page, "query_selector"):
                shipping_blocked_el = page.query_selector(site.selectors.shipping_blocked_notice)

            if shipping_blocked_el is not None:
                is_visible = True
                if hasattr(shipping_blocked_el, "is_visible"):
                    is_visible = shipping_blocked_el.is_visible()
                if is_visible:
                    raise AssertionError("Nenhum método de envio disponível para os EUA (.woocommerce-no-shipping-available-html visível)")

            step_latencies["shipping_check"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 6: Verificação de Gateways de Pagamento
            # =========================================================================
            current_phase = "payment_gateways"
            t0 = time.perf_counter()
            payment_el = None
            if hasattr(page, "query_selector"):
                payment_el = page.query_selector(site.selectors.payment_gateways_container)

            if payment_el is None:
                raise AssertionError("Recipientes de métodos de pagamento ausentes ou não encontrados no DOM (#payment)")

            if hasattr(payment_el, "is_visible") and not payment_el.is_visible():
                raise AssertionError("Recipientes de métodos de pagamento ausentes ou não visíveis no checkout")

            step_latencies["payment_gateways"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # Sucesso integral de todas as etapas!
            total_duration = round((time.perf_counter() - start_global) * 1000.0, 2)
            code_errors, long_tasks, perf_metrics, slowest_requests = self.extract_telemetry(page, buffer, current_phase)

            return ProbeResult(
                site_id=site.id,
                timestamp=datetime.now(timezone.utc),
                success=True,
                completed_step="payment_gateways",
                step_latencies_ms=step_latencies,
                total_duration_ms=total_duration,
                js_errors=buffer.js_errors,
                console_errors=buffer.console_errors,
                failed_ajax_calls=buffer.failed_ajax_calls,
                verdict_pt="Checkout 100% operacional para compradores nos EUA",
                code_errors=code_errors,
                long_tasks=long_tasks,
                performance=perf_metrics,
                slowest_requests=slowest_requests,
            )

        except Exception as exc:
            total_duration = round((time.perf_counter() - start_global) * 1000.0, 2)
            screenshot_path, dom_extract = self.capture_evidence(page, site.id, current_phase)
            verdict = build_verdict_pt(current_phase, buffer, custom_reason=str(exc) if "AssertionError" in str(type(exc)) else None)
            code_errors, long_tasks, perf_metrics, slowest_requests = self.extract_telemetry(page, buffer, current_phase)

            incident = ForensicIncident(
                incident_id=f"INC-{site.id}-{int(time.time())}",
                site_id=site.id,
                site_name=site.name,
                timestamp=datetime.now(timezone.utc),
                failure_phase=current_phase,
                verdict_pt=verdict,
                screenshot_path=screenshot_path,
                js_errors=buffer.js_errors,
                failed_ajax_calls=buffer.failed_ajax_calls,
                dom_extract=dom_extract,
                error_details=str(exc),
                code_errors=code_errors,
                long_tasks=long_tasks,
                slowest_requests=slowest_requests,
            )

            return ProbeResult(
                site_id=site.id,
                timestamp=datetime.now(timezone.utc),
                success=False,
                completed_step=current_phase,
                step_latencies_ms=step_latencies,
                total_duration_ms=total_duration,
                js_errors=buffer.js_errors,
                console_errors=buffer.console_errors,
                failed_ajax_calls=buffer.failed_ajax_calls,
                screenshot_path=screenshot_path,
                dom_extract=dom_extract,
                verdict_pt=verdict,
                incident=incident,
                code_errors=code_errors,
                long_tasks=long_tasks,
                performance=perf_metrics,
                slowest_requests=slowest_requests,
            )

    def probe_site(
        self,
        site: SiteConfig,
        thresholds: Optional[ThresholdsConfig] = None,
        waf_bypass_token: Optional[str] = None,
        page_override: Optional[Any] = None,
        headless: bool = True,
    ) -> ProbeResult:
        """
        Executa a sonda Playwright. Se page_override for fornecido, executa diretamente na página (útil para testes).
        Caso contrário, inicializa o contexto Chromium Playwright com perfil US.
        """
        if thresholds is None:
            thresholds = ThresholdsConfig()

        buffer = ForensicBuffer()

        # Injeção para testes determinísticos
        if page_override is not None:
            self.attach_forensic_listeners(page_override, buffer, thresholds.http_error_threshold)
            return self.run_flow_on_page(page_override, site, thresholds, buffer)

        # Execução com Playwright real
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "O pacote 'playwright' não está instalado no ambiente. "
                "Execute: pip install playwright && playwright install chromium"
            )

        token = waf_bypass_token or os.environ.get("WAF_BYPASS_TOKEN")
        extra_headers = dict(site.custom_headers)
        if token:
            extra_headers[site.waf_bypass_header_name] = token

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                context = browser.new_context(
                    user_agent=CHROME_USER_AGENT,
                    viewport=DEFAULT_VIEWPORT,
                    locale=DEFAULT_LOCALE,
                    timezone_id=DEFAULT_TIMEZONE,
                    extra_http_headers=extra_headers,
                )
                page = context.new_page()
                self.attach_forensic_listeners(page, buffer, thresholds.http_error_threshold)
                return self.run_flow_on_page(page, site, thresholds, buffer)
            finally:
                browser.close()
