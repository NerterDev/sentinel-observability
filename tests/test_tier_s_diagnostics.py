"""Testes determinísticos do Motor de Diagnóstico Avançado Tier-S (TASK-006).

Valida:
  1. Extração estruturada de erros de código JavaScript (parse_js_error).
  2. Telemetria de Long Tasks (>50ms) e cálculo de Total Blocking Time (TBT).
  3. Mini-waterfall de requisições lentas e breakdown de recursos (PerformanceMetrics).
  4. Geração e persistência atómica de dossiês forenses (DiagnosticsDossier).
"""

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import tempfile
import json

from src.models import (
    CodeErrorDetail,
    DiagnosticsDossier,
    HealthStatus,
    LongTaskDetail,
    PerformanceMetrics,
    SlowRequestDetail,
    StoreStatus,
)
from src.browser_probe import parse_js_error, BrowserProbeEngine, ForensicBuffer
from src.forensic_recorder import ForensicRecorder


class TestTierSDiagnostics(unittest.TestCase):
    """Suíte de testes para os recursos do diagnóstico Tier-S."""

    def test_parse_js_error_structured_stack_trace(self):
        """Garante extração de tipo de erro, mensagem, ficheiro, linha e coluna de stack trace."""
        err_msg = "TypeError: Cannot read properties of undefined (reading 'init')"
        stack = (
            "TypeError: Cannot read properties of undefined (reading 'init')\n"
            "    at https://example.com/wp-content/plugins/woocommerce/assets/js/checkout.js:42:15\n"
            "    at Array.forEach (<anonymous>)"
        )
        error_type, source_file, line_no, col_no = parse_js_error(err_msg, stack)

        self.assertEqual(error_type, "TypeError")
        self.assertEqual(source_file, "https://example.com/wp-content/plugins/woocommerce/assets/js/checkout.js")
        self.assertEqual(line_no, 42)
        self.assertEqual(col_no, 15)

    def test_parse_js_error_unhandled_rejection(self):
        """Garante classificação de unhandled error type sem stack."""
        err_msg = "ReferenceError: jQuery is not defined"
        error_type, source_file, line_no, col_no = parse_js_error(err_msg, None)

        self.assertEqual(error_type, "ReferenceError")
        self.assertIsNone(source_file)
        self.assertIsNone(line_no)
        self.assertIsNone(col_no)

    def test_extract_telemetry_tbt_and_byte_breakdown(self):
        """Valida o cálculo do TBT (tarefas > 50ms) e divisão de bytes por recurso."""
        engine = BrowserProbeEngine()
        buffer = ForensicBuffer()

        buffer.requests_log = [
            {"url": "https://store.com/app.js", "method": "GET", "status": 200, "duration_ms": 450.0, "resource_type": "script", "content_type": "application/javascript", "size_bytes": 100000, "cache_status": "HIT"},
            {"url": "https://store.com/style.css", "method": "GET", "status": 200, "duration_ms": 120.0, "resource_type": "stylesheet", "content_type": "text/css", "size_bytes": 20000, "cache_status": "HIT"},
            {"url": "https://store.com/hero.jpg", "method": "GET", "status": 200, "duration_ms": 300.0, "resource_type": "image", "content_type": "image/jpeg", "size_bytes": 150000, "cache_status": "MISS"},
            {"url": "https://store.com/font.woff2", "method": "GET", "status": 200, "duration_ms": 50.0, "resource_type": "font", "content_type": "font/woff2", "size_bytes": 30000, "cache_status": "HIT"},
            {"url": "https://store.com/ajax.php", "method": "POST", "status": 500, "duration_ms": 600.0, "resource_type": "xhr", "content_type": "application/json", "size_bytes": 500, "cache_status": "DYNAMIC"},
            {"url": "https://store.com/analytics.js", "method": "GET", "status": 200, "duration_ms": 90.0, "resource_type": "script", "content_type": "application/javascript", "size_bytes": 15000, "cache_status": "HIT"},
        ]

        mock_page = MagicMock()
        mock_page.evaluate.return_value = {
            "longTasks": [
                {"duration": 120.0, "startTime": 300.0, "name": "self", "attribution": "script.js"},
                {"duration": 40.0, "startTime": 500.0, "name": "self", "attribution": "fast.js"}, # <= 50ms não bloqueia
                {"duration": 80.0, "startTime": 700.0, "name": "self", "attribution": "heavy.js"},
            ],
            "fcpMs": 250.0,
            "domContentLoadedMs": 400.0,
            "loadEventMs": 850.0,
            "unhandledErrors": [],
        }

        code_errors, long_tasks, perf, slowest = engine.extract_telemetry(mock_page, buffer, "checkout")

        # TBT: (120 - 50) + (80 - 50) = 70 + 30 = 100ms
        self.assertEqual(perf.total_blocking_time_ms, 100.0)
        self.assertEqual(perf.long_tasks_count, 3)
        self.assertEqual(perf.fcp_ms, 250.0)
        self.assertEqual(perf.dom_content_loaded_ms, 400.0)
        self.assertEqual(perf.load_event_ms, 850.0)

        # Bytes
        self.assertEqual(perf.js_bytes, 115000)
        self.assertEqual(perf.css_bytes, 20000)
        self.assertEqual(perf.img_bytes, 150000)
        self.assertEqual(perf.font_bytes, 30000)
        self.assertEqual(perf.total_transferred_bytes, 315500)
        self.assertEqual(perf.requests_count, 6)

        # Top 5 slowest ordenadas decrescente por duration_ms
        self.assertEqual(len(slowest), 5)
        self.assertEqual(slowest[0].url, "https://store.com/ajax.php")
        self.assertEqual(slowest[0].duration_ms, 600.0)
        self.assertEqual(slowest[1].url, "https://store.com/app.js")
        self.assertEqual(slowest[1].duration_ms, 450.0)

    def test_save_dossier_atomic_persistence(self):
        """Garante que ForensicRecorder grava dossiês em formato JSON atómico."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recorder = ForensicRecorder(data_dir=tmp_dir)
            dossier = DiagnosticsDossier(
                site_id="txrace",
                site_name="TX Race",
                timestamp=datetime.now(timezone.utc),
                status=HealthStatus.HEALTHY,
                verdict_pt="Checkout fluido e 0 erros de JavaScript.",
                cf_cache_status="HIT",
                content_encoding="br",
                http_version="HTTP/2",
                ttfb_ms=130.0,
                code_errors=[],
                console_errors=[],
                long_tasks=[],
                performance=PerformanceMetrics(
                    total_blocking_time_ms=0.0,
                    long_tasks_count=0,
                    fcp_ms=120.0,
                    dom_content_loaded_ms=250.0,
                    load_event_ms=500.0,
                    total_transferred_bytes=45000,
                    js_bytes=20000,
                    css_bytes=10000,
                    img_bytes=15000,
                    font_bytes=0,
                    requests_count=5,
                ),
                slowest_requests=[],
                failed_requests=[],
            )

            file_path = recorder.save_dossier(dossier)
            self.assertTrue(file_path.is_file())
            self.assertEqual(file_path.name, "txrace.json")

            data = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(data["site_id"], "txrace")
            self.assertEqual(data["verdict_pt"], "Checkout fluido e 0 erros de JavaScript.")
            self.assertEqual(data["performance"]["js_bytes"], 20000)
            self.assertEqual(data["cf_cache_status"], "HIT")


if __name__ == "__main__":
    unittest.main()
