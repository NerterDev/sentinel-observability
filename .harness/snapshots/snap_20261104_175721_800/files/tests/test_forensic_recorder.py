"""
Testes Determinísticos — Gravador Forense e Histórico GitOps (TASK-003)
Plataforma de Observabilidade Web (Tier-S)
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from src.forensic_recorder import ForensicRecorder
from src.models import (
    CurrentStatusPayload,
    ForensicIncident,
    HealthStatus,
    HistoryPayload,
    HistoryPoint,
    InfrastructureType,
    StoreStatus,
)


class TestForensicRecorder(unittest.TestCase):
    """Testes da camada de persistência atómica, série temporal e métricas."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.recorder = ForensicRecorder(data_dir=self.data_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_atomic_write_json(self):
        """Verifica se a gravação atómica cria ficheiro JSON legível e limpa temporários."""
        target_file = self.data_dir / "teste_atomico.json"
        payload = HistoryPayload(retention_days=15)

        self.recorder.atomic_write_json(target_file, payload)
        self.assertTrue(target_file.exists())

        # Verifica se não ficaram ficheiros temporários órfãos (.tmp)
        tmp_files = list(self.data_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

        # Validação do conteúdo
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["retention_days"], 15)

    def test_compute_metrics_for_site(self):
        """Valida cálculos de uptime, taxa de checkout e TTFB médio."""
        now = datetime.now(timezone.utc)
        points = [
            HistoryPoint(timestamp=now, site_id="loja-a", status=HealthStatus.HEALTHY, ttfb_ms=200.0, checkout_success=True),
            HistoryPoint(timestamp=now, site_id="loja-a", status=HealthStatus.DEGRADED, ttfb_ms=600.0, checkout_success=True),
            HistoryPoint(timestamp=now, site_id="loja-a", status=HealthStatus.CRITICAL, ttfb_ms=1000.0, checkout_success=False),
            HistoryPoint(timestamp=now, site_id="loja-a", status=HealthStatus.HEALTHY, ttfb_ms=400.0, checkout_success=True),
        ]

        uptime, checkout_rate, avg_ttfb = self.recorder.compute_metrics_for_site("loja-a", points)

        # Uptime: 3 em 4 runs != CRITICAL -> 75%
        self.assertEqual(uptime, 75.0)
        # Checkout: 3 em 4 bem sucedidos -> 75%
        self.assertEqual(checkout_rate, 75.0)
        # TTFB médio: (200 + 600 + 1000 + 400) / 4 = 550.0
        self.assertEqual(avg_ttfb, 550.0)

    def test_sliding_window_pruning_30_days(self):
        """Verifica se registos com mais de 30 dias são descartados automaticamente."""
        now = datetime.now(timezone.utc)
        day45_ago = now - timedelta(days=45)
        day35_ago = now - timedelta(days=35)
        day10_ago = now - timedelta(days=10)
        day1_ago = now - timedelta(days=1)

        old_points = [
            HistoryPoint(timestamp=day45_ago, site_id="loja-1", status=HealthStatus.HEALTHY, checkout_success=True),
            HistoryPoint(timestamp=day35_ago, site_id="loja-1", status=HealthStatus.HEALTHY, checkout_success=True),
            HistoryPoint(timestamp=day10_ago, site_id="loja-1", status=HealthStatus.HEALTHY, checkout_success=True),
        ]

        # Pré-grava histórico antigo
        initial_history = HistoryPayload(retention_days=30, points=old_points)
        self.recorder.atomic_write_json(self.recorder.history_path, initial_history)

        # Novo ponto de hoje
        new_point = HistoryPoint(timestamp=now, site_id="loja-1", status=HealthStatus.HEALTHY, checkout_success=True)
        store = StoreStatus(
            site_id="loja-1",
            name="Loja 1",
            infrastructure_type=InfrastructureType.ROCKET_CLOUDFLARE,
        )

        self.recorder.record_run(
            new_statuses=[store],
            new_points=[new_point],
            retention_days=30,
            now=now,
        )

        # Recarrega histórico atualizado
        updated = self.recorder.load_history()
        # Apenas day10_ago e now devem permanecer (2 pontos). day45 e day35 devem ser podados.
        self.assertEqual(len(updated.points), 2)
        timestamps = [p.timestamp for p in updated.points]
        self.assertIn(now, timestamps)
        self.assertIn(day10_ago, timestamps)
        self.assertNotIn(day45_ago, timestamps)
        self.assertNotIn(day35_ago, timestamps)

    def test_save_incident(self):
        """Verifica gravação individual de dossiê de anomalia em dashboard/data/incidents/."""
        inc = ForensicIncident(
            incident_id="INC-TEST-001",
            site_id="loja-x",
            site_name="Loja X",
            failure_phase="shipping_check",
            verdict_pt="Nenhum método de envio disponível para os EUA",
            screenshot_path="public/screenshots/loja_x.png",
        )

        path = self.recorder.save_incident(inc)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "INC-TEST-001.json")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["incident_id"], "INC-TEST-001")
            self.assertEqual(data["verdict_pt"], "Nenhum método de envio disponível para os EUA")


if __name__ == "__main__":
    unittest.main()

