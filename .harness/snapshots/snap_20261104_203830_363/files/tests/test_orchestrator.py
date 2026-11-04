"""
Testes Determinísticos — Orquestrador Central Multi-Site (TASK-003)
Plataforma de Observabilidade Web (Tier-S)
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from src.models import (
    EdgeInspectionResult,
    ForensicIncident,
    HealthStatus,
    ProbeResult,
    SiteConfig,
    SitesConfigFile,
    ThresholdsConfig,
)
from src.orchestrator import (
    determine_consolidated_status,
    load_configurations,
    run_observability_pipeline,
)


class TestOrchestrator(unittest.TestCase):
    """Testes do orquestrador central e resiliência multi-loja."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.config_dir = self.base_dir / "config"
        self.output_dir = self.base_dir / "dashboard/data"
        self.screenshots_dir = self.base_dir / "public/screenshots"

        self.config_dir.mkdir(parents=True)
        self.output_dir.mkdir(parents=True)
        self.screenshots_dir.mkdir(parents=True)

        # Configurações de teste
        self.site_a = SiteConfig(
            id="loja-a",
            name="Loja A Rocket",
            store_url="https://loja-a.com",
            product_url="https://loja-a.com/p1",
        )
        self.site_b = SiteConfig(
            id="loja-b",
            name="Loja B VPS",
            store_url="https://loja-b.com",
            product_url="https://loja-b.com/p2",
        )

        sites_cfg = SitesConfigFile(sites=[self.site_a, self.site_b])
        thresholds_cfg = ThresholdsConfig()

        with open(self.config_dir / "sites.json", "w", encoding="utf-8") as f:
            f.write(sites_cfg.model_dump_json(indent=2))

        with open(self.config_dir / "thresholds.json", "w", encoding="utf-8") as f:
            f.write(thresholds_cfg.model_dump_json(indent=2))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_determine_consolidated_status(self):
        """Valida a matriz combinatória de status consolidado entre edge e browser probe."""
        edge_healthy = EdgeInspectionResult(site_id="s1", status=HealthStatus.HEALTHY)
        edge_degraded = EdgeInspectionResult(site_id="s1", status=HealthStatus.DEGRADED)
        edge_critical = EdgeInspectionResult(site_id="s1", status=HealthStatus.CRITICAL)

        probe_success = ProbeResult(site_id="s1", success=True)
        probe_failure = ProbeResult(site_id="s1", success=False)
        probe_with_js_error = ProbeResult(site_id="s1", success=True, js_errors=[{"message": "err"}])

        # 1. Ambos saudáveis -> HEALTHY
        self.assertEqual(determine_consolidated_status(edge_healthy, probe_success), HealthStatus.HEALTHY)

        # 2. Edge crítico -> CRITICAL (mesmo se probe não rodou)
        self.assertEqual(determine_consolidated_status(edge_critical, None), HealthStatus.CRITICAL)

        # 3. Edge saudável mas checkout falhou -> CRITICAL
        self.assertEqual(determine_consolidated_status(edge_healthy, probe_failure), HealthStatus.CRITICAL)

        # 4. Edge degradado -> DEGRADED
        self.assertEqual(determine_consolidated_status(edge_degraded, probe_success), HealthStatus.DEGRADED)

        # 5. Checkout com erro JS menor -> DEGRADED
        self.assertEqual(determine_consolidated_status(edge_healthy, probe_with_js_error), HealthStatus.DEGRADED)

    def test_run_observability_pipeline_success_mocked(self):
        """Executa pipeline completa com mocks de inspeção e verifica JSONs gerados."""
        def mock_edge(site, thresholds, token):
            return EdgeInspectionResult(
                site_id=site.id,
                dns_resolved_ip="192.0.2.1",
                ssl_valid=True,
                ssl_days_remaining=60,
                ttfb_ms=220.0,
                status=HealthStatus.HEALTHY,
            )

        mock_browser = MagicMock()
        mock_browser.probe_site.return_value = ProbeResult(
            site_id="loja-a",
            success=True,
            completed_step="payment_gateways",
            total_duration_ms=4500.0,
        )

        summary = run_observability_pipeline(
            config_dir=self.config_dir,
            output_dir=self.output_dir,
            screenshots_dir=self.screenshots_dir,
            edge_inspector_override=mock_edge,
            browser_engine_override=mock_browser,
        )

        self.assertEqual(summary["total_monitored"], 2)
        self.assertEqual(summary["healthy_count"], 2)
        self.assertEqual(summary["critical_count"], 0)

        # Verifica se os ficheiros GitOps foram gravados atomicamente
        status_file = self.output_dir / "current_status.json"
        history_file = self.output_dir / "history.json"

        self.assertTrue(status_file.exists())
        self.assertTrue(history_file.exists())

        with open(status_file, "r", encoding="utf-8") as f:
            status_data = json.load(f)
            self.assertEqual(len(status_data["stores"]), 2)
            self.assertEqual(status_data["stores"][0]["status"], "HEALTHY")

    def test_run_observability_pipeline_site_filter(self):
        """Verifica se a flag de filtro de loja monitoriza apenas o site especificado."""
        def mock_edge(site, thresholds, token):
            return EdgeInspectionResult(site_id=site.id, dns_resolved_ip="192.0.2.1", ssl_valid=True)

        summary = run_observability_pipeline(
            config_dir=self.config_dir,
            output_dir=self.output_dir,
            screenshots_dir=self.screenshots_dir,
            target_site_id="loja-b",
            skip_browser=True,
            edge_inspector_override=mock_edge,
        )

        self.assertEqual(summary["total_monitored"], 1)
        self.assertEqual(summary["healthy_count"], 1)

    def test_run_observability_pipeline_fault_isolation(self):
        """
        Garante a Lei de Resiliência: falha fatal na Loja A não pode impedir
        a execução nem a gravação dos dados da Loja B.
        """
        def mock_edge_flaky(site, thresholds, token):
            if site.id == "loja-a":
                raise RuntimeError("Falha de conexão severa ou kernel panic")
            return EdgeInspectionResult(
                site_id=site.id,
                dns_resolved_ip="192.0.2.1",
                ssl_valid=True,
                ttfb_ms=180.0,
                status=HealthStatus.HEALTHY,
            )

        mock_browser = MagicMock()
        mock_browser.probe_site.return_value = ProbeResult(
            site_id="loja-b",
            success=True,
            completed_step="payment_gateways",
        )

        summary = run_observability_pipeline(
            config_dir=self.config_dir,
            output_dir=self.output_dir,
            screenshots_dir=self.screenshots_dir,
            edge_inspector_override=mock_edge_flaky,
            browser_engine_override=mock_browser,
        )

        # Ambas as lojas foram processadas e registradas
        self.assertEqual(summary["total_monitored"], 2)
        # Loja A é CRITICAL, Loja B é HEALTHY
        self.assertEqual(summary["critical_count"], 1)
        self.assertEqual(summary["healthy_count"], 1)
        self.assertGreaterEqual(summary["incidents_recorded"], 1)


if __name__ == "__main__":
    unittest.main()

