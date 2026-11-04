"""
Orquestrador Central Multi-Site e Pipeline de Observabilidade
Plataforma de Observabilidade Web (Tier-S)
Caminho Canónico: src/orchestrator.py
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from src.browser_probe import BrowserProbeEngine
from src.edge_inspector import inspect_edge
from src.forensic_recorder import ForensicRecorder
from src.models import (
    EdgeInspectionResult,
    ForensicIncident,
    HealthStatus,
    HistoryPoint,
    ProbeResult,
    SiteConfig,
    SitesConfigFile,
    StoreStatus,
    ThresholdsConfig,
)


def load_configurations(
    config_dir: Path,
) -> tuple[SitesConfigFile, ThresholdsConfig]:
    """Carrega e valida estritamente os ficheiros sites.json e thresholds.json."""
    sites_path = config_dir / "sites.json"
    thresholds_path = config_dir / "thresholds.json"

    if not sites_path.exists():
        raise FileNotFoundError(f"Ficheiro de configuração não encontrado: {sites_path}")
    if not thresholds_path.exists():
        raise FileNotFoundError(f"Ficheiro de limiares não encontrado: {thresholds_path}")

    with open(sites_path, "r", encoding="utf-8") as f:
        sites_cfg = SitesConfigFile.model_validate_json(f.read())

    with open(thresholds_path, "r", encoding="utf-8") as f:
        thresholds_cfg = ThresholdsConfig.model_validate_json(f.read())

    return sites_cfg, thresholds_cfg


def determine_consolidated_status(
    edge_res: EdgeInspectionResult,
    probe_res: Optional[ProbeResult],
) -> HealthStatus:
    """
    Consolida o estado operacional combinando os dados da borda e da sonda de checkout.
    """
    # 1. Falha crítica se o edge caiu ou se o checkout falhou
    if edge_res.status == HealthStatus.CRITICAL:
        return HealthStatus.CRITICAL

    if probe_res is not None and not probe_res.success:
        return HealthStatus.CRITICAL

    # 2. Estado degradado se edge estiver lento ou se houver erros menores de JS/console
    if edge_res.status == HealthStatus.DEGRADED:
        return HealthStatus.DEGRADED

    if probe_res is not None and (len(probe_res.js_errors) > 0 or len(probe_res.console_errors) > 0):
        return HealthStatus.DEGRADED

    return HealthStatus.HEALTHY


def run_observability_pipeline(
    config_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    screenshots_dir: Optional[Path] = None,
    target_site_id: Optional[str] = None,
    skip_browser: bool = False,
    waf_bypass_token: Optional[str] = None,
    browser_engine_override: Optional[Any] = None,
    edge_inspector_override: Optional[Any] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Ponto de entrada central para a execução da bateria de observabilidade multi-loja.
    Resiliência: falha em uma loja nunca aborta o processamento das restantes lojas.
    """
    config_path = config_dir or Path("config")
    output_path = output_dir or Path("dashboard/data")
    screenshots_path = screenshots_dir or Path("public/screenshots")

    sites_cfg, thresholds = load_configurations(config_path)

    # Filtra lojas ativas ou loja alvo específica
    candidates = [s for s in sites_cfg.sites if s.enabled]
    if target_site_id:
        candidates = [s for s in candidates if s.id == target_site_id]
        if not candidates:
            raise ValueError(f"Loja ativa com id '{target_site_id}' não encontrada em sites.json")

    recorder = ForensicRecorder(data_dir=output_path)
    browser_engine = browser_engine_override or BrowserProbeEngine(screenshots_dir=screenshots_path)
    run_now = now or datetime.now(timezone.utc)

    all_statuses: List[StoreStatus] = []
    all_points: List[HistoryPoint] = []
    all_incidents: List[ForensicIncident] = []

    print(f"[{run_now.isoformat()}] A iniciar ronda de observabilidade ({len(candidates)} lojas)...")

    for site in candidates:
        print(f"  -> Inspecionando: {site.name} ({site.id}) [{site.infrastructure_type.value}]")
        try:
            # 1. Sonda de Borda / Rede (Edge Inspector)
            if edge_inspector_override is not None:
                edge_res = edge_inspector_override(site, thresholds, waf_bypass_token)
            else:
                edge_res = inspect_edge(site, thresholds, waf_bypass_token)

            # 2. Sonda de Browser Playwright (apenas se não for ignorada e se DNS responder)
            probe_res = None
            if not skip_browser and edge_res.dns_resolved_ip:
                try:
                    probe_res = browser_engine.probe_site(
                        site=site,
                        thresholds=thresholds,
                        waf_bypass_token=waf_bypass_token,
                    )
                except Exception as probe_exc:
                    # Captura falha no motor de browser sem abortar
                    probe_res = ProbeResult(
                        site_id=site.id,
                        success=False,
                        completed_step="browser_launch_failure",
                        verdict_pt=f"Falha de inicialização do browser: {str(probe_exc)}",
                        incident=ForensicIncident(
                            incident_id=f"INC-{site.id}-{int(run_now.timestamp())}",
                            site_id=site.id,
                            site_name=site.name,
                            timestamp=run_now,
                            failure_phase="browser_launch",
                            verdict_pt=f"Falha ao iniciar sonda Playwright: {str(probe_exc)}",
                            error_details=str(probe_exc),
                        ),
                    )

            # 3. Consolidação de Saúde e Incidentes
            consolidated_health = determine_consolidated_status(edge_res, probe_res)

            # Determina o incidente ativo a registar
            active_incident = None
            if probe_res and probe_res.incident:
                active_incident = probe_res.incident
                all_incidents.append(active_incident)
            elif edge_res.status == HealthStatus.CRITICAL:
                active_incident = ForensicIncident(
                    incident_id=f"INC-{site.id}-EDGE-{int(run_now.timestamp())}",
                    site_id=site.id,
                    site_name=site.name,
                    timestamp=run_now,
                    failure_phase="edge_network",
                    verdict_pt=edge_res.error_message or "Indisponibilidade crítica de rede ou TLS/SSL",
                    http_status=edge_res.http_status_code,
                    error_details=edge_res.error_message,
                )
                all_incidents.append(active_incident)

            # 4. Criação do estado instantâneo (StoreStatus)
            store_status = StoreStatus(
                site_id=site.id,
                name=site.name,
                infrastructure_type=site.infrastructure_type,
                status=consolidated_health,
                ssl_days_remaining=edge_res.ssl_days_remaining,
                latest_ttfb_ms=edge_res.ttfb_ms,
                last_checked_at=run_now,
                last_incident=active_incident,
            )
            all_statuses.append(store_status)

            # 5. Criação do ponto da série temporal (HistoryPoint)
            checkout_ok = probe_res.success if probe_res else (consolidated_health != HealthStatus.CRITICAL)
            total_duration = probe_res.total_duration_ms if probe_res else edge_res.total_latency_ms

            history_pt = HistoryPoint(
                timestamp=run_now,
                site_id=site.id,
                status=consolidated_health,
                ttfb_ms=edge_res.ttfb_ms,
                checkout_success=checkout_ok,
                total_duration_ms=total_duration,
                incident_id=active_incident.incident_id if active_incident else None,
            )
            all_points.append(history_pt)

            print(f"     Resultado: {consolidated_health.value} (TTFB: {edge_res.ttfb_ms}ms, Checkout: {'OK' if checkout_ok else 'FALHA'})")

        except Exception as loop_err:
            # Isolamento total de falha: regista como crítico e avança para a próxima loja
            print(f"     [ERRO CRÍTICO NÃO TRATADO EM {site.id}]: {str(loop_err)}")
            error_inc = ForensicIncident(
                incident_id=f"INC-{site.id}-FATAL-{int(run_now.timestamp())}",
                site_id=site.id,
                site_name=site.name,
                timestamp=run_now,
                failure_phase="fatal_loop_error",
                verdict_pt=f"Erro não tratado na execução da sonda: {str(loop_err)}",
                error_details=str(loop_err),
            )
            all_incidents.append(error_inc)
            all_statuses.append(
                StoreStatus(
                    site_id=site.id,
                    name=site.name,
                    infrastructure_type=site.infrastructure_type,
                    status=HealthStatus.CRITICAL,
                    last_checked_at=run_now,
                    last_incident=error_inc,
                )
            )
            all_points.append(
                HistoryPoint(
                    timestamp=run_now,
                    site_id=site.id,
                    status=HealthStatus.CRITICAL,
                    checkout_success=False,
                    incident_id=error_inc.incident_id,
                )
            )

    # 6. Gravação GitOps Consolidada
    recorder.record_run(
        new_statuses=all_statuses,
        new_points=all_points,
        incidents=all_incidents,
        now=run_now,
    )

    summary = {
        "timestamp": run_now.isoformat(),
        "total_monitored": len(all_statuses),
        "healthy_count": sum(1 for s in all_statuses if s.status == HealthStatus.HEALTHY),
        "degraded_count": sum(1 for s in all_statuses if s.status == HealthStatus.DEGRADED),
        "critical_count": sum(1 for s in all_statuses if s.status == HealthStatus.CRITICAL),
        "incidents_recorded": len(all_incidents),
    }

    print("\n--- RESUMO DA RONDA DE OBSERVABILIDADE ---")
    print(f"Lojas testadas: {summary['total_monitored']}")
    print(f"  - HEALTHY:  {summary['healthy_count']}")
    print(f"  - DEGRADED: {summary['degraded_count']}")
    print(f"  - CRITICAL: {summary['critical_count']}")
    print(f"Novos incidentes arquivados: {summary['incidents_recorded']}")
    print("-------------------------------------------\n")

    return summary


def main():
    """Interface CLI para execução via linha de comandos ou GitHub Actions Runner."""
    parser = argparse.ArgumentParser(
        description="Orquestrador Central da Plataforma de Observabilidade Web (Tier-S)"
    )
    parser.add_argument("--site", dest="target_site", help="ID da loja específica a inspecionar")
    parser.add_argument("--config-dir", default="config", help="Diretório dos ficheiros sites.json e thresholds.json")
    parser.add_argument("--output-dir", default="dashboard/data", help="Diretório de destino dos ficheiros JSON")
    parser.add_argument("--screenshots-dir", default="public/screenshots", help="Diretório de destino dos screenshots")
    parser.add_argument("--skip-browser", action="store_true", help="Executa apenas a inspeção de borda (DNS, SSL, TTFB)")
    parser.add_argument("--waf-bypass-token", help="Token para cabeçalho de bypass de WAF/Cloudflare")

    args = parser.parse_args()

    try:
        run_observability_pipeline(
            config_dir=Path(args.config_dir),
            output_dir=Path(args.output_dir),
            screenshots_dir=Path(args.screenshots_dir),
            target_site_id=args.target_site,
            skip_browser=args.skip_browser,
            waf_bypass_token=args.waf_bypass_token,
        )
        sys.exit(0)
    except Exception as e:
        print(f"ERRO FATAL NA EXECUÇÃO DO ORQUESTRADOR: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

