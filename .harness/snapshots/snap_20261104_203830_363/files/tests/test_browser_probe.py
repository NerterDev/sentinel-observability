"""
Testes Determinísticos — Motor Playwright de Sonda Forense (TASK-002)
Plataforma de Observabilidade Web (Tier-S)
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.models import (
    ForensicIncident,
    InfrastructureType,
    ProbeResult,
    SiteConfig,
    ThresholdsConfig,
)
from src.browser_probe import (
    BrowserProbeEngine,
    CHROME_USER_AGENT,
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    DEFAULT_VIEWPORT,
    ForensicBuffer,
    build_verdict_pt,
)


class TestForensicBuffer(unittest.TestCase):
    """Testes dos intercetores em tempo real de logs JS, consola e respostas HTTP."""

    def test_on_page_error(self):
        buffer = ForensicBuffer()
        mock_error = MagicMock()
        mock_error.__str__.return_value = "Uncaught TypeError: Cannot read property 'value' of null"
        mock_error.stack = "TypeError: Cannot read property 'value' of null\n    at checkout.js:42:15"

        buffer.on_page_error(mock_error)
        self.assertEqual(len(buffer.js_errors), 1)
        self.assertIn("Uncaught TypeError", buffer.js_errors[0]["message"])
        self.assertIn("checkout.js:42:15", buffer.js_errors[0]["stack"])

    def test_on_console_message_filters_errors(self):
        buffer = ForensicBuffer()

        # Mensagem informativa (deve ser ignorada)
        msg_info = MagicMock()
        msg_info.type = "log"
        msg_info.text = "Analytics initialized"
        buffer.on_console_message(msg_info)
        self.assertEqual(len(buffer.console_errors), 0)

        # Mensagem de erro (deve ser capturada)
        msg_err = MagicMock()
        msg_err.type = "error"
        msg_err.text = "Failed to load Stripe iframe element"
        buffer.on_console_message(msg_err)
        self.assertEqual(len(buffer.console_errors), 1)
        self.assertIn("Stripe iframe", buffer.console_errors[0])

    def test_on_response_captures_ajax_and_status_error(self):
        buffer = ForensicBuffer()

        # Resposta 200 normal (deve ser ignorada)
        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.url = "https://loja.com/wp-content/themes/style.css"
        buffer.on_response(resp_ok)
        self.assertEqual(len(buffer.failed_ajax_calls), 0)

        # Chamada wc-ajax com erro 500
        resp_ajax = MagicMock()
        resp_ajax.status = 500
        resp_ajax.url = "https://loja.com/?wc-ajax=update_order_review"
        resp_ajax.request.method = "POST"
        resp_ajax.text.return_value = '{"error": "Internal Server Error in WooCommerce"}'
        buffer.on_response(resp_ajax)

        self.assertEqual(len(buffer.failed_ajax_calls), 1)
        ajax_entry = buffer.failed_ajax_calls[0]
        self.assertEqual(ajax_entry["status"], 500)
        self.assertEqual(ajax_entry["method"], "POST")
        self.assertIn("wc-ajax=update_order_review", ajax_entry["url"])
        self.assertIn("Internal Server Error", ajax_entry["body_preview"])


class TestVerdictPtGeneration(unittest.TestCase):
    """Testes da geração de diagnósticos claros em português."""

    def test_verdict_shipping_blocked(self):
        buffer = ForensicBuffer()
        verdict = build_verdict_pt("shipping_check", buffer)
        self.assertEqual(verdict, "Nenhum método de envio disponível para os EUA")

    def test_verdict_js_error(self):
        buffer = ForensicBuffer()
        buffer.js_errors.append({"message": "ReferenceError: Stripe is not defined"})
        verdict = build_verdict_pt("checkout_navigation", buffer)
        self.assertIn("Erro de JS impediu cálculo do checkout", verdict)
        self.assertIn("Stripe is not defined", verdict)

    def test_verdict_wc_ajax_failure(self):
        buffer = ForensicBuffer()
        buffer.failed_ajax_calls.append({
            "url": "https://loja.com/?wc-ajax=checkout&step=review",
            "status": 503,
        })
        verdict = build_verdict_pt("order_review", buffer)
        self.assertIn("Falha assíncrona no endpoint WooCommerce (wc-ajax=checkout, HTTP 503)", verdict)

    def test_verdict_payment_gateways_missing(self):
        buffer = ForensicBuffer()
        verdict = build_verdict_pt("payment_gateways", buffer)
        self.assertEqual(verdict, "Recipientes de métodos de pagamento ausentes ou não renderizados")

    def test_verdict_order_review_timeout(self):
        buffer = ForensicBuffer()
        verdict = build_verdict_pt("order_review", buffer)
        self.assertEqual(verdict, "Timeout ao aguardar atualização da tabela de pedido (#order_review)")


class TestBrowserProbeEngineFlow(unittest.TestCase):
    """Testes determinísticos do fluxo de 6 etapas e captura de evidência forense."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = BrowserProbeEngine(screenshots_dir=Path(self.temp_dir.name))
        self.site = SiteConfig(
            id="loja-teste-us",
            name="Loja Teste US",
            store_url="https://loja.exemplo.com",
            product_url="https://loja.exemplo.com/produto/camisa/",
            infrastructure_type=InfrastructureType.ROCKET_CLOUDFLARE,
        )
        self.thresholds = ThresholdsConfig(step_timeout_sec=10)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_checkout_flow_full_success(self):
        """Simula execução bem-sucedida de todas as 6 etapas."""
        mock_page = MagicMock()
        mock_page.url = "https://loja.exemplo.com/checkout/"

        # Mock dos seletores de frete e gateway
        mock_payment_el = MagicMock()
        mock_payment_el.is_visible.return_value = True

        def query_selector_side_effect(selector):
            if selector == self.site.selectors.shipping_blocked_notice:
                return None  # Frete NÃO está bloqueado
            if selector == self.site.selectors.payment_gateways_container:
                return mock_payment_el
            return MagicMock()

        mock_page.query_selector.side_effect = query_selector_side_effect

        result = self.engine.probe_site(
            site=self.site,
            thresholds=self.thresholds,
            page_override=mock_page,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.completed_step, "payment_gateways")
        self.assertIsNone(result.incident)
        self.assertIn("product_page", result.step_latencies_ms)
        self.assertIn("add_to_cart", result.step_latencies_ms)
        self.assertIn("order_review", result.step_latencies_ms)
        self.assertIn("payment_gateways", result.step_latencies_ms)

        # Valida chamadas aos seletores corretos
        mock_page.goto.assert_any_call(self.site.product_url, timeout=10000.0, wait_until="domcontentloaded")
        mock_page.click.assert_called_with(self.site.selectors.add_to_cart_btn)

    def test_checkout_flow_shipping_blocked_failure(self):
        """Simula detecção do seletor .woocommerce-no-shipping-available-html."""
        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body><div class='woocommerce-no-shipping-available-html'>No shipping</div></body></html>"

        mock_shipping_blocked = MagicMock()
        mock_shipping_blocked.is_visible.return_value = True

        def query_selector_side_effect(selector):
            if selector == self.site.selectors.shipping_blocked_notice:
                return mock_shipping_blocked
            return MagicMock()

        mock_page.query_selector.side_effect = query_selector_side_effect

        result = self.engine.probe_site(
            site=self.site,
            thresholds=self.thresholds,
            page_override=mock_page,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.completed_step, "shipping_check")
        self.assertIsNotNone(result.incident)
        self.assertEqual(result.incident.failure_phase, "shipping_check")
        self.assertIn("Nenhum método de envio disponível para os EUA", result.incident.verdict_pt)
        mock_page.screenshot.assert_called_once()

    def test_checkout_flow_payment_gateways_missing_failure(self):
        """Simula ausência de gateways de pagamento no checkout."""
        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body>Sem métodos de pagamento</body></html>"

        def query_selector_side_effect(selector):
            if selector == self.site.selectors.shipping_blocked_notice:
                return None
            if selector == self.site.selectors.payment_gateways_container:
                return None  # Não encontrou #payment
            return MagicMock()

        mock_page.query_selector.side_effect = query_selector_side_effect

        result = self.engine.probe_site(
            site=self.site,
            thresholds=self.thresholds,
            page_override=mock_page,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.completed_step, "payment_gateways")
        self.assertIsNotNone(result.incident)
        self.assertIn("Recipientes de métodos de pagamento", result.incident.verdict_pt)
        mock_page.screenshot.assert_called_once()

    def test_checkout_flow_order_review_timeout_failure(self):
        """Simula timeout ao aguardar tabela #order_review."""
        mock_page = MagicMock()

        def wait_for_selector_side_effect(selector, **kwargs):
            if selector == self.site.selectors.order_review_table:
                raise TimeoutError("Timeout 10000ms waiting for #order_review")
            return MagicMock()

        mock_page.wait_for_selector.side_effect = wait_for_selector_side_effect

        result = self.engine.probe_site(
            site=self.site,
            thresholds=self.thresholds,
            page_override=mock_page,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.completed_step, "order_review")
        self.assertIsNotNone(result.incident)
        self.assertIn("Timeout", result.incident.verdict_pt)
        mock_page.screenshot.assert_called_once()


class TestPlaywrightContextConfiguration(unittest.TestCase):
    """Testa se os parâmetros do Chromium correspondem estritamente ao perfil US."""

    @patch("src.browser_probe.BrowserProbeEngine.run_flow_on_page")
    def test_browser_context_arguments(self, mock_run_flow):
        mock_run_flow.return_value = ProbeResult(
            site_id="loja-us",
            success=True,
            completed_step="payment_gateways",
        )

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        mock_sync_api = MagicMock()
        mock_sync_api.sync_playwright.return_value.__enter__.return_value = mock_playwright

        site = SiteConfig(
            id="loja-us",
            name="Loja US",
            store_url="https://loja.com",
            product_url="https://loja.com/p",
            custom_headers={"X-Custom": "val1"},
        )

        with patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.sync_api": mock_sync_api}):
            engine = BrowserProbeEngine()
            result = engine.probe_site(site=site, waf_bypass_token="secret-123")

            self.assertTrue(result.success)
            mock_browser.new_context.assert_called_once_with(
                user_agent=CHROME_USER_AGENT,
                viewport=DEFAULT_VIEWPORT,
                locale=DEFAULT_LOCALE,
                timezone_id=DEFAULT_TIMEZONE,
                extra_http_headers={"X-Custom": "val1", "X-WAF-Bypass-Token": "secret-123"},
            )
            mock_browser.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
