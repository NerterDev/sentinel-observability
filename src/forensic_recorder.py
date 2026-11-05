"""
Gravador Forense e Gestor de Histórico GitOps (Tier-S)
Plataforma de Observabilidade Web
Caminho Canónico: src/forensic_recorder.py
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel

from src.models import (
    CurrentStatusPayload,
    DiagnosticsDossier,
    ForensicIncident,
    HealthStatus,
    HistoryPayload,
    HistoryPoint,
    StoreStatus,
)


class ForensicRecorder:
    """
    Controlador de persistência GitOps com gravação atómica, manutenção de série temporal
    deslizante de 30 dias, arquivo de dossiês de incidentes e perfis diagnósticos.
    """

    def __init__(self, data_dir: Optional[Any] = None):
        self.data_dir = Path(data_dir) if data_dir is not None else Path("dashboard/data")
        self.current_status_path = self.data_dir / "current_status.json"
        self.history_path = self.data_dir / "history.json"
        self.incidents_dir = self.data_dir / "incidents"
        self.dossiers_dir = self.data_dir / "dossiers"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Garante a existência das pastas necessárias para persistência."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.incidents_dir.mkdir(parents=True, exist_ok=True)
        self.dossiers_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def atomic_write_json(file_path: Path, payload: BaseModel) -> None:
        """
        Grava um ficheiro JSON de forma estritamente atómica:
        escreve num ficheiro temporário e realiza os.replace para prevenir corrupção.
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)
        json_str = payload.model_dump_json(indent=2)

        # Ficheiro temporário no mesmo diretório para garantir o mesmo volume/disco
        with tempfile.NamedTemporaryFile(
            dir=file_path.parent,
            delete=False,
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
        ) as tmp:
            tmp.write(json_str)
            tmp_path = Path(tmp.name)

        try:
            os.replace(tmp_path, file_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise

    def load_history(self) -> HistoryPayload:
        """Carrega a série temporal existente em history.json de forma segura."""
        if not self.history_path.exists():
            return HistoryPayload()
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return HistoryPayload()
                return HistoryPayload.model_validate_json(content)
        except Exception:
            # Em caso de ficheiro corrompido ou inválido, inicia histórico limpo
            return HistoryPayload()

    def load_current_status(self) -> CurrentStatusPayload:
        """Carrega o estado instantâneo existente em current_status.json."""
        if not self.current_status_path.exists():
            return CurrentStatusPayload()
        try:
            with open(self.current_status_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return CurrentStatusPayload()
                return CurrentStatusPayload.model_validate_json(content)
        except Exception:
            return CurrentStatusPayload()

    @staticmethod
    def compute_metrics_for_site(
        site_id: str,
        points: List[HistoryPoint],
    ) -> Tuple[float, float, Optional[float]]:
        """
        Calcula as estatísticas consolidadas dos últimos 30 dias para uma loja:
        Retorna: (uptime_pct_30d, checkout_success_rate_pct, average_ttfb_ms)
        """
        site_points = [p for p in points if p.site_id == site_id]
        if not site_points:
            return 100.0, 100.0, None

        total_runs = len(site_points)

        # 1. Uptime: runs onde status != CRITICAL
        available_runs = sum(1 for p in site_points if p.status != HealthStatus.CRITICAL)
        uptime_pct = round((available_runs / total_runs) * 100.0, 2)

        # 2. Checkout Success Rate: runs onde a compra foi simulada com sucesso
        checkout_successes = sum(1 for p in site_points if p.checkout_success)
        checkout_rate = round((checkout_successes / total_runs) * 100.0, 2)

        # 3. TTFB Médio
        ttfb_values = [p.ttfb_ms for p in site_points if p.ttfb_ms is not None and p.ttfb_ms > 0]
        avg_ttfb = round(sum(ttfb_values) / len(ttfb_values), 2) if ttfb_values else None

        return uptime_pct, checkout_rate, avg_ttfb

    def save_incident(self, incident: ForensicIncident) -> Path:
        """Grava o relatório forense individual em dashboard/data/incidents/<id>.json."""
        file_path = self.incidents_dir / f"{incident.incident_id}.json"
        self.atomic_write_json(file_path, incident)
        return file_path

    def save_dossier(self, dossier: DiagnosticsDossier) -> Path:
        """Grava o dossiê de telemetria completa em dashboard/data/dossiers/{site_id}.json."""
        file_path = self.dossiers_dir / f"{dossier.site_id}.json"
        self.atomic_write_json(file_path, dossier)
        return file_path

    def record_run(
        self,
        new_statuses: List[StoreStatus],
        new_points: List[HistoryPoint],
        incidents: Optional[List[ForensicIncident]] = None,
        dossiers: Optional[List[DiagnosticsDossier]] = None,
        retention_days: int = 30,
        now: Optional[datetime] = None,
    ) -> None:
        """
        Regista o resultado de uma bateria completa de monitorização:
        1. Arquiva dossiês de incidentes individuais e dossiês por loja.
        2. Atualiza a série temporal em history.json, podando registos com mais de 30 dias.
        3. Recalcula as métricas estatísticas dos últimos 30 dias para cada loja.
        4. Grava current_status.json atomicamente.
        """
        now_dt = now or datetime.now(timezone.utc)
        if incidents:
            for inc in incidents:
                self.save_incident(inc)

        if dossiers:
            for dos in dossiers:
                self.save_dossier(dos)

        # 1. Rotação temporal deslizante (Pruning)
        cutoff_dt = now_dt - timedelta(days=retention_days)
        history = self.load_history()

        # Combina histórico prévio com novos pontos
        all_points = history.points + new_points
        # Filtra apenas pontos dentro da janela dos últimos 30 dias
        pruned_points = [p for p in all_points if p.timestamp >= cutoff_dt]
        # Ordena cronologicamente
        pruned_points.sort(key=lambda p: p.timestamp)

        # 2. Atualização das métricas nos cartões de status
        for store in new_statuses:
            uptime, checkout_rate, avg_ttfb = self.compute_metrics_for_site(
                store.site_id, pruned_points
            )
            store.uptime_pct_30d = uptime
            store.checkout_success_rate_pct = checkout_rate
            store.average_ttfb_ms = avg_ttfb
            store.last_checked_at = now_dt

        # 3. Gravação atómica de history.json
        updated_history = HistoryPayload(
            retention_days=retention_days,
            updated_at=now_dt,
            points=pruned_points,
        )
        self.atomic_write_json(self.history_path, updated_history)

        # 4. Gravação atómica de current_status.json
        status_payload = CurrentStatusPayload(
            updated_at=now_dt,
            stores=new_statuses,
        )
        self.atomic_write_json(self.current_status_path, status_payload)

