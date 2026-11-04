"""
Testes Determinísticos — Modelos de Dados e Edge Inspector (TASK-001)
Plataforma de Observabilidade Web (Tier-S)
"""

from datetime import datetime, timedelta, timezone
import json
import os
import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch

import httpx
from pydantic import ValidationError

from src.models import (
    EdgeInspectionResult,
    HealthStatus,
    InfrastructureType,
    SiteConfig,
    SiteSelectors,
    SitesConfigFile,
    ThresholdsConfig,
)
from src.edge_inspector import (
    check_ssl,
    classify_health,
    inspect_all_sites,
    inspect_edge,
    measure_http,
    resolve_dns,
)


class TestModelsAndSchemas(unittest.TestCase):
    """Testes de validação dos esquemas Pydantic autoritativos."""

    def test_valid_site_config(self):
        site = SiteConfig(
            id="loja-teste",
            name="Loja Teste",
            store_url="https://loja.exemplo.com",
            product_url="https://loja.exemplo.com/produto/item-1",
            infrastructure_type=InfrastructureType.ROCKET_CLOUDFLARE,
        )
        self.assertEqual(site.id, "loja-teste")
        self.assertEqual(site.selectors.add_to_cart_btn, "button[name='add-to-cart'], .single_add_to_cart_button")
        self.assertTrue(site.enabled)
        self.assertEqual(site.waf_bypass_header_name, "X-WAF-Bypass-Token")

    def test_invalid_site_id_regex(self):
        with self.assertRaises(ValidationError):
            SiteConfig(
                id="Loja Inválida Com Espaços",
                name="Loja Inválida",
                store_url="https://exemplo.com",
                product_url="https://exemplo.com/p",
            )

    def test_invalid_url_scheme(self):
        with self.assertRaises(ValidationError):
            SiteConfig(
                id="loja-ftp",
                name="Loja FTP",
                store_url="ftp://exemplo.com",
                product_url="ftp://exemplo.com/p",
            )

    def test_duplicate_site_ids_rejected(self):
        sites = [
            SiteConfig(id="loja-a", name="Loja A", store_url="https://a.com", product_url="https://a.com/p"),
            SiteConfig(id="loja-a", name="Loja A Duplicada", store_url="https://a2.com", product_url="https://a2.com/p"),
        ]
        with self.assertRaises(ValidationError):
            SitesConfigFile(sites=sites)

    def test_thresholds_order_validation(self):
        # ttfb_warning >= ttfb_critical deve falhar
        with self.assertRaises(ValidationError):
            ThresholdsConfig(ttfb_warning_ms=2000.0, ttfb_critical_ms=1000.0)

        # ssl_warning <= ssl_critical deve falhar
        with self.assertRaises(ValidationError):
            ThresholdsConfig(ssl_expiry_warning_days=2, ssl_expiry_critical_days=5)

    def test_canonical_files_on_disk(self):
        """Verifica se config/sites.json e config/thresholds.json cumprem os schemas."""
        with open("config/sites.json", "r", encoding="utf-8") as f:
            sites_data = json.load(f)
            sites_cfg = SitesConfigFile.model_validate(sites_data)
            self.assertGreaterEqual(len(sites_cfg.sites), 3)

        with open("config/thresholds.json", "r", encoding="utf-8") as f:
            thresh_data = json.load(f)
            thresh_cfg = ThresholdsConfig.model_validate(thresh_data)
            self.assertEqual(thresh_cfg.ttfb_warning_ms, 800.0)
            self.assertEqual(thresh_cfg.ttfb_critical_ms, 2500.0)


class TestEdgeInspectorNetwork(unittest.TestCase):
    """Testes determinísticos das funções de rede, DNS, SSL e HTTP."""

    @patch("socket.getaddrinfo")
    def test_resolve_dns_success(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 0))
        ]
        ip, elapsed_ms, err = resolve_dns("loja.exemplo.com")
        self.assertEqual(ip, "192.0.2.1")
        self.assertIsNone(err)
        self.assertGreaterEqual(elapsed_ms, 0.0)

    @patch("socket.getaddrinfo")
    def test_resolve_dns_failure(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror(-2, "Name or service not known")
        ip, elapsed_ms, err = resolve_dns("inexistente.invalido")
        self.assertIsNone(ip)
        self.assertIn("Erro de DNS", err)

    @patch("socket.create_connection")
    def test_check_ssl_valid(self, mock_create_conn):
        future_date = datetime.now(timezone.utc) + timedelta(days=45)
        formatted_date = future_date.strftime("%b %d %H:%M:%S %Y GMT")

        mock_sock = MagicMock()
        mock_ssl_sock = MagicMock()
        mock_ssl_sock.getpeercert.return_value = {
            "issuer": ((("organizationName", "Let's Encrypt"),),),
            "notAfter": formatted_date,
        }

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__.return_value = mock_ssl_sock
        mock_create_conn.return_value.__enter__.return_value = mock_sock

        valid, issuer, expiry, days, err = check_ssl(
            "loja.exemplo.com", ssl_context=mock_context
        )
        self.assertTrue(valid)
        self.assertEqual(issuer, "Let's Encrypt")
        self.assertGreaterEqual(days, 44)
        self.assertIsNone(err)

    @patch("socket.create_connection")
    def test_check_ssl_expired(self, mock_create_conn):
        past_date = datetime.now(timezone.utc) - timedelta(days=10)
        formatted_date = past_date.strftime("%b %d %H:%M:%S %Y GMT")

        mock_sock = MagicMock()
        mock_ssl_sock = MagicMock()
        mock_ssl_sock.getpeercert.return_value = {
            "issuer": ((("commonName", "Exemplo Invalido"),),),
            "notAfter": formatted_date,
        }

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__.return_value = mock_ssl_sock
        mock_create_conn.return_value.__enter__.return_value = mock_sock

        valid, issuer, expiry, days, err = check_ssl(
            "loja.exemplo.com", ssl_context=mock_context
        )
        self.assertFalse(valid)
        self.assertLess(days, 0)
        self.assertIn("expirou", err)

    def test_measure_http_success_and_waf_bypass(self):
        captured_headers = {}

        def mock_handler(request: httpx.Request):
            nonlocal captured_headers
            captured_headers = dict(request.headers)
            return httpx.Response(200, text="<html><body>Loja OK</body></html>")

        transport = httpx.MockTransport(mock_handler)
        client = httpx.Client(transport=transport)

        status, ttfb, total_lat, bypass_applied, err = measure_http(
            url="https://loja.exemplo.com/produto/camisa",
            waf_bypass_token="secret-token-123",
            waf_bypass_header_name="X-WAF-Bypass-Token",
            client=client,
        )

        self.assertEqual(status, 200)
        self.assertTrue(bypass_applied)
        self.assertIsNone(err)
        self.assertEqual(captured_headers.get("x-waf-bypass-token"), "secret-token-123")
        self.assertGreaterEqual(ttfb, 0.0)

    def test_measure_http_server_error(self):
        def mock_handler(request: httpx.Request):
            return httpx.Response(502, text="Bad Gateway Cloudflare")

        transport = httpx.MockTransport(mock_handler)
        client = httpx.Client(transport=transport)

        status, ttfb, total_lat, bypass_applied, err = measure_http(
            url="https://loja.exemplo.com",
            client=client,
        )

        self.assertEqual(status, 502)
        self.assertIn("HTTP 502", err)


class TestHealthClassification(unittest.TestCase):
    """Testes da matriz de classificação determinística do estado operacional."""

    def setUp(self):
        self.thresholds = ThresholdsConfig(
            ttfb_warning_ms=800.0,
            ttfb_critical_ms=2500.0,
            ssl_expiry_warning_days=15,
            ssl_expiry_critical_days=3,
        )

    def test_classify_healthy(self):
        result = EdgeInspectionResult(
            site_id="loja-ok",
            dns_resolved_ip="192.0.2.1",
            ssl_valid=True,
            ssl_days_remaining=40,
            ttfb_ms=250.0,
            http_status_code=200,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.HEALTHY)

    def test_classify_degraded_by_ttfb(self):
        result = EdgeInspectionResult(
            site_id="loja-lenta",
            dns_resolved_ip="192.0.2.1",
            ssl_valid=True,
            ssl_days_remaining=30,
            ttfb_ms=1200.0,  # Entre 800 e 2500
            http_status_code=200,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.DEGRADED)

    def test_classify_degraded_by_ssl_expiry(self):
        result = EdgeInspectionResult(
            site_id="loja-ssl-aviso",
            dns_resolved_ip="192.0.2.1",
            ssl_valid=True,
            ssl_days_remaining=10,  # <= 15 dias
            ttfb_ms=300.0,
            http_status_code=200,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.DEGRADED)

    def test_classify_critical_by_dns_failure(self):
        result = EdgeInspectionResult(
            site_id="loja-sem-dns",
            dns_resolved_ip=None,
            ssl_valid=False,
            http_status_code=None,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.CRITICAL)

    def test_classify_critical_by_ssl_expired(self):
        result = EdgeInspectionResult(
            site_id="loja-ssl-critico",
            dns_resolved_ip="192.0.2.1",
            ssl_valid=True,
            ssl_days_remaining=2,  # <= 3 dias
            ttfb_ms=300.0,
            http_status_code=200,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.CRITICAL)

    def test_classify_critical_by_http_500(self):
        result = EdgeInspectionResult(
            site_id="loja-500",
            dns_resolved_ip="192.0.2.1",
            ssl_valid=True,
            ssl_days_remaining=60,
            ttfb_ms=200.0,
            http_status_code=500,
        )
        self.assertEqual(classify_health(result, self.thresholds), HealthStatus.CRITICAL)


class TestInspectEdgeIntegrationMocked(unittest.TestCase):
    """Testes de fluxo completo de inspect_edge e inspect_all_sites com mocks controlados."""

    @patch("src.edge_inspector.resolve_dns")
    @patch("src.edge_inspector.check_ssl")
    @patch("src.edge_inspector.measure_http")
    def test_inspect_edge_success(self, mock_http, mock_ssl, mock_dns):
        mock_dns.return_value = ("192.0.2.1", 15.0, None)
        mock_ssl.return_value = (True, "Cloudflare Inc", datetime.now(timezone.utc) + timedelta(days=90), 90, None)
        mock_http.return_value = (200, 320.0, 480.0, True, None)

        site = SiteConfig(
            id="rocket-site",
            name="Loja Rocket",
            store_url="https://rocket.example.com",
            product_url="https://rocket.example.com/item-1",
            infrastructure_type=InfrastructureType.ROCKET_CLOUDFLARE,
        )

        result = inspect_edge(site, waf_bypass_token="token-xyz")
        self.assertEqual(result.site_id, "rocket-site")
        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertEqual(result.http_status_code, 200)
        self.assertTrue(result.waf_bypass_applied)
        self.assertEqual(result.ssl_days_remaining, 90)
        self.assertIsNone(result.error_message)

    @patch("src.edge_inspector.inspect_edge")
    def test_inspect_all_sites_filtering(self, mock_inspect):
        site_enabled = SiteConfig(
            id="site-ativo", name="Ativo", store_url="https://ativo.com", product_url="https://ativo.com/p", enabled=True
        )
        site_disabled = SiteConfig(
            id="site-inativo", name="Inativo", store_url="https://inativo.com", product_url="https://inativo.com/p", enabled=False
        )

        mock_inspect.return_value = EdgeInspectionResult(
            site_id="site-ativo",
            status=HealthStatus.HEALTHY,
        )

        results = inspect_all_sites([site_enabled, site_disabled])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].site_id, "site-ativo")
        mock_inspect.assert_called_once()


if __name__ == "__main__":
    unittest.main()

