# Relatório de Integridade de Engenharia — TASK-003

## Identificação
- **Tarefa:** TASK-003: Gravador Forense, Histórico GitOps Deslizante e Orquestrador Central
- **Data:** 2026-11-04
- **Autoridade de Esquema:** `src/models.py`
- **Caminho Canónico:** `src/orchestrator.py` e `src/forensic_recorder.py`

## Princípios Cumpridos
1. **One Source of Truth & Zero Redundância:** Os dados consolidados em `dashboard/data/current_status.json` e `history.json` são a única fonte de dados consumida pelo frontend SPA.
2. **Atomic Writes:** Toda a escrita em disco utiliza `tempfile` e rename atómico (`os.replace`) para evitar corrupção em caso de cancelamento abrupto do runner.
3. **Sliding Window Garbage Collection:** Registos com mais de 30 dias são automaticamente podados da série temporal, mantendo o repositório leve para operações GitOps contínuas.
4. **Fault Isolation:** A falha de inspeção em uma loja é tratada como evento de telemetria, permitindo que a execução prossiga para as restantes lojas sem falhas catastróficas.

