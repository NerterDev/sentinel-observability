"""
Motor Playwright de Sonda Forense Sintética e Interceção Ativa
Plataforma de Observabilidade Web (Tier-S)
Caminho Canónico: src/browser_probe.py
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import uuid

from src.models import (
    ForensicIncident,
    ProbeResult,
    SiteConfig,
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


@dataclass
class ForensicBuffer:
    """Buffer acumulador em tempo real de eventos da consola, erros JS e rede."""
    js_errors: List[Dict[str, Any]] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    failed_ajax_calls: List[Dict[str, Any]] = field(default_factory=list)

    def on_page_error(self, error: Any) -> None:
        """Captura exceções de execução JavaScript não tratadas."""
        err_msg = str(error)
        stack = getattr(error, "stack", None)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": err_msg,
            "stack": str(stack) if stack else None,
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

        try:
            # =========================================================================
            # ETAPA 1: Página do Produto
            # =========================================================================
            current_phase = "product_page"
            t0 = time.perf_counter()
            page.goto(site.product_url, timeout=timeout_ms, wait_until="domcontentloaded")
            step_latencies["product_page"] = round((time.perf_counter() - t0) * 1000.0, 2)

            # =========================================================================
            # ETAPA 2: Adicionar ao Carrinho
            # =========================================================================
            current_phase = "add_to_cart"
            t0 = time.perf_counter()
            # Localiza e clica no botão de adicionar ao carrinho
            page.wait_for_selector(site.selectors.add_to_cart_btn, timeout=timeout_ms)
            page.click(site.selectors.add_to_cart_btn)

            # Aguarda feedback visual ou transição
            # Tenta encontrar a mensagem de sucesso ou mudança no carrinho
            try:
                page.wait_for_selector(site.selectors.cart_feedback, timeout=min(timeout_ms, 8000.0))
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
            )

        except Exception as exc:
            total_duration = round((time.perf_counter() - start_global) * 1000.0, 2)
            screenshot_path, dom_extract = self.capture_evidence(page, site.id, current_phase)
            verdict = build_verdict_pt(current_phase, buffer, custom_reason=str(exc) if "AssertionError" in str(type(exc)) else None)

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
