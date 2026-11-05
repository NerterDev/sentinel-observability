"""
Edge Inspector — Motor de Sonda de Rede, DNS, TLS/SSL e TTFB
Plataforma de Observabilidade Web (Tier-S)
Caminho Canónico: src/edge_inspector.py
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Tuple
import socket
import ssl
import time
from urllib.parse import urlparse

import httpx

from src.models import (
    EdgeInspectionResult,
    HealthStatus,
    SiteConfig,
    ThresholdsConfig,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def resolve_dns(hostname: str, timeout: float = 5.0) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Resolve o endereço IP do hostname e mede o tempo de resposta do DNS.
    Retorna: (ip_resolvido, lookup_time_ms, mensagem_erro)
    """
    start = time.perf_counter()
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        duration_ms = (time.perf_counter() - start) * 1000.0
        if addr_info and len(addr_info) > 0:
            resolved_ip = addr_info[0][4][0]
            return resolved_ip, round(duration_ms, 2), None
        return None, round(duration_ms, 2), "Nenhum endereço retornado na resolução DNS"
    except socket.gaierror as e:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return None, round(duration_ms, 2), f"Erro de DNS (gaierror): {str(e)}"
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return None, round(duration_ms, 2), f"Falha na resolução de DNS: {str(e)}"
    finally:
        socket.setdefaulttimeout(old_timeout)


def check_ssl(
    hostname: str,
    port: int = 443,
    timeout: float = 5.0,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> Tuple[bool, Optional[str], Optional[datetime], Optional[int], Optional[str]]:
    """
    Inspeciona o handshake TLS/SSL e calcula os dias restantes de validade.
    Retorna: (ssl_valido, emissor, data_expiracao, dias_restantes, erro)
    """
    if ssl_context is None:
        ssl_context = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ssl_context.wrap_socket(sock, server_hostname=hostname) as ssl_sock:
                cert = ssl_sock.getpeercert()
                if not cert:
                    return False, None, None, None, "Certificado vazio ou não retornado pelo servidor"

                # Extrai emissor (Organization name ou Common name)
                issuer_parts = []
                for field in cert.get("issuer", ()):
                    for k, v in field:
                        if k in ("organizationName", "commonName"):
                            issuer_parts.append(v)
                issuer_str = " / ".join(issuer_parts) if issuer_parts else "Desconhecido"

                # Extrai data de expiração (notAfter formato: 'May 10 12:00:00 2026 GMT')
                not_after_str = cert.get("notAfter")
                if not not_after_str:
                    return False, issuer_str, None, None, "Campo notAfter ausente no certificado"

                # Parse da data
                not_after_dt = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                days_remaining = (not_after_dt - now_utc).days

                is_valid = days_remaining >= 0
                error_msg = None if is_valid else f"Certificado SSL expirou há {abs(days_remaining)} dias"

                return is_valid, issuer_str, not_after_dt, days_remaining, error_msg

    except ssl.SSLCertVerificationError as e:
        return False, None, None, 0, f"Falha de verificação SSL: {e.verify_message or str(e)}"
    except ssl.SSLError as e:
        return False, None, None, None, f"Erro TLS/SSL: {str(e)}"
    except (socket.timeout, TimeoutError):
        return False, None, None, None, f"Timeout ({timeout}s) ao negociar TLS/SSL com {hostname}:{port}"
    except ConnectionRefusedError:
        return False, None, None, None, f"Conexão recusada ao tentar handshake TLS em {hostname}:{port}"
    except Exception as e:
        return False, None, None, None, f"Falha na verificação TLS: {str(e)}"


def measure_http(
    url: str,
    custom_headers: Optional[Dict[str, str]] = None,
    waf_bypass_token: Optional[str] = None,
    waf_bypass_header_name: str = "X-WAF-Bypass-Token",
    timeout: float = 10.0,
    client: Optional[httpx.Client] = None,
    extra_diagnostics: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[int], Optional[float], Optional[float], bool, Optional[str]]:
    """
    Executa requisição HTTP e mede TTFB (Time To First Byte) e latência total.
    Retorna: (http_status, ttfb_ms, total_latency_ms, bypass_aplicado, erro)
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if custom_headers:
        headers.update(custom_headers)

    # Injeta header de bypass WAF se existir
    bypass_token = waf_bypass_token or os.environ.get("WAF_BYPASS_TOKEN")
    bypass_applied = False
    if bypass_token:
        headers[waf_bypass_header_name] = bypass_token
        bypass_applied = True

    close_client = False
    if client is None:
        client = httpx.Client(follow_redirects=True, timeout=timeout)
        close_client = True

    try:
        start_time = time.perf_counter()
        # Streaming para capturar com precisão o momento da receção dos cabeçalhos (TTFB)
        with client.stream("GET", url, headers=headers) as response:
            ttfb_duration_ms = (time.perf_counter() - start_time) * 1000.0
            # Consome o corpo da resposta para medir latência completa
            _ = response.read()
            total_duration_ms = (time.perf_counter() - start_time) * 1000.0

            status_code = response.status_code
            error_msg = None
            if status_code >= 400:
                error_msg = f"HTTP {status_code}: Resposta de erro do servidor"

            if extra_diagnostics is not None:
                extra_diagnostics["cf_cache_status"] = response.headers.get("cf-cache-status")
                extra_diagnostics["content_encoding"] = response.headers.get("content-encoding")
                extra_diagnostics["server"] = response.headers.get("server")
                extra_diagnostics["http_version"] = getattr(response, "http_version", None)

            return status_code, round(ttfb_duration_ms, 2), round(total_duration_ms, 2), bypass_applied, error_msg

    except httpx.ConnectTimeout:
        return None, None, None, bypass_applied, f"Timeout de conexão ({timeout}s) ao aceder {url}"
    except httpx.ReadTimeout:
        return None, None, None, bypass_applied, f"Timeout de leitura ({timeout}s) ao esperar dados de {url}"
    except httpx.ConnectError as e:
        return None, None, None, bypass_applied, f"Falha de conexão a {url}: {str(e)}"
    except httpx.HTTPError as e:
        return None, None, None, bypass_applied, f"Erro HTTP ao aceder {url}: {str(e)}"
    except Exception as e:
        return None, None, None, bypass_applied, f"Erro inesperado no acesso HTTP a {url}: {str(e)}"
    finally:
        if close_client:
            client.close()


def classify_health(
    result: EdgeInspectionResult,
    thresholds: ThresholdsConfig,
) -> HealthStatus:
    """
    Classifica deterministicamente o estado operacional da borda e rede.
    Retorna: HealthStatus (HEALTHY, DEGRADED, CRITICAL)
    """
    # 1. Falhas Críticas
    if not result.dns_resolved_ip:
        return HealthStatus.CRITICAL

    if not result.ssl_valid:
        return HealthStatus.CRITICAL

    if result.ssl_days_remaining is not None and result.ssl_days_remaining <= thresholds.ssl_expiry_critical_days:
        return HealthStatus.CRITICAL

    if result.http_status_code is None or result.http_status_code >= 500:
        return HealthStatus.CRITICAL

    if result.ttfb_ms is not None and result.ttfb_ms >= thresholds.ttfb_critical_ms:
        return HealthStatus.CRITICAL

    # 2. Estados Degradados / Avisos
    if result.ssl_days_remaining is not None and result.ssl_days_remaining <= thresholds.ssl_expiry_warning_days:
        return HealthStatus.DEGRADED

    if result.ttfb_ms is not None and result.ttfb_ms >= thresholds.ttfb_warning_ms:
        return HealthStatus.DEGRADED

    if result.http_status_code is not None and result.http_status_code >= thresholds.http_error_threshold:
        return HealthStatus.DEGRADED

    return HealthStatus.HEALTHY


def inspect_edge(
    site: SiteConfig,
    thresholds: Optional[ThresholdsConfig] = None,
    waf_bypass_token: Optional[str] = None,
    timeout: float = 10.0,
    http_client: Optional[httpx.Client] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> EdgeInspectionResult:
    """
    Executa a bateria completa de inspeção de borda para uma loja específica.
    Garante resiliência: erros capturados geram resultado estruturado sem levantar exceções não tratadas.
    """
    if thresholds is None:
        thresholds = ThresholdsConfig()

    parsed = urlparse(site.store_url)
    hostname = parsed.hostname or site.store_url.split("/")[0]
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    is_https = parsed.scheme == "https" or port == 443

    # 1. Resolução DNS
    dns_ip, dns_time_ms, dns_error = resolve_dns(hostname, timeout=min(timeout, 5.0))

    # 2. TLS/SSL Check (se for HTTPS)
    ssl_valid = False
    ssl_issuer = None
    ssl_expiry = None
    ssl_days = None
    ssl_error = None

    if is_https and dns_ip:
        ssl_valid, ssl_issuer, ssl_expiry, ssl_days, ssl_error = check_ssl(
            hostname=hostname,
            port=port,
            timeout=min(timeout, 5.0),
            ssl_context=ssl_context,
        )
    elif not is_https:
        # Se for explicitamente http:// em ambiente de teste local
        ssl_valid = True
        ssl_issuer = "N/A (HTTP)"

    # 3. Medição HTTP & TTFB
    target_url = site.product_url if site.product_url else site.store_url
    edge_diag: Dict[str, Any] = {}
    http_status, ttfb_ms, total_latency, bypass_applied, http_error = measure_http(
        url=target_url,
        custom_headers=site.custom_headers,
        waf_bypass_token=waf_bypass_token,
        waf_bypass_header_name=site.waf_bypass_header_name,
        timeout=timeout,
        client=http_client,
        extra_diagnostics=edge_diag,
    )

    # Consolidação de mensagens de erro
    errors = [e for e in (dns_error, ssl_error, http_error) if e]
    if ttfb_ms is not None and thresholds and ttfb_ms >= thresholds.ttfb_critical_ms:
        errors.append(f"TTFB crítico ({ttfb_ms:.0f}ms excedeu limiar crítico de {thresholds.ttfb_critical_ms:.0f}ms)")
    consolidated_error = " | ".join(errors) if errors else None

    # Construção do objeto de resultado
    result = EdgeInspectionResult(
        site_id=site.id,
        timestamp=datetime.now(timezone.utc),
        dns_resolved_ip=dns_ip,
        dns_lookup_time_ms=dns_time_ms,
        ssl_valid=ssl_valid,
        ssl_issuer=ssl_issuer,
        ssl_expiry_date=ssl_expiry,
        ssl_days_remaining=ssl_days,
        ttfb_ms=ttfb_ms,
        total_latency_ms=total_latency,
        http_status_code=http_status,
        waf_bypass_applied=bypass_applied,
        error_message=consolidated_error,
        diagnostics={
            "hostname": hostname,
            "port": port,
            "infrastructure_type": site.infrastructure_type.value,
            "target_url": target_url,
            "cf_cache_status": edge_diag.get("cf_cache_status"),
            "content_encoding": edge_diag.get("content_encoding"),
            "server": edge_diag.get("server"),
            "http_version": edge_diag.get("http_version"),
        },
    )

    # Classificação final do estado operacional
    result.status = classify_health(result, thresholds)
    return result


def inspect_all_sites(
    sites: List[SiteConfig],
    thresholds: Optional[ThresholdsConfig] = None,
    waf_bypass_token: Optional[str] = None,
    max_workers: int = 5,
) -> List[EdgeInspectionResult]:
    """
    Executa a inspeção concorrente para uma lista de lojas.
    Ignora lojas desativadas (enabled=False).
    """
    active_sites = [s for s in sites if s.enabled]
    if not active_sites:
        return []

    results: List[EdgeInspectionResult] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(active_sites))) as executor:
        futures = {
            executor.submit(inspect_edge, site, thresholds, waf_bypass_token): site
            for site in active_sites
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                site = futures[future]
                # Fallback de segurança extrema: garante que nunca perde o registo de uma loja
                results.append(
                    EdgeInspectionResult(
                        site_id=site.id,
                        status=HealthStatus.CRITICAL,
                        error_message=f"Erro fatal não tratado na thread da loja: {str(e)}",
                    )
                )

    return sorted(results, key=lambda r: r.site_id)

