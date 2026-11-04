# Relatório de Integridade de Engenharia — TASK-002

## Identificação
- **Tarefa:** TASK-002: Motor Playwright de Sonda Forense e Interceção Ativa (browser_probe.py)
- **Data:** 2026-11-04
- **Autoridade de Esquema:** `src/models.py`
- **Caminho Canónico:** `src/browser_probe.py`

## Princípios Cumpridos
1. **Canonical Path First:** Toda a lógica de interação Playwright e captura forense fica centralizada em `src/browser_probe.py`, sem wrappers desnecessários.
2. **Zero Footprint Compliance:** O motor opera estritamente como consumidor externo, sem requisições privilegiadas ou injeção de scripts no WordPress.
3. **Data Trace Completo:** Ingress (`SiteConfig`) -> Validação de seletores -> Estado (buffers intercetores e medição) -> Egress (`ProbeResult` e screenshots).
4. **Resiliência a Falhas:** Timeouts e quebras em qualquer etapa do checkout são convertidos deterministicamente em `ForensicIncident` com veredito em português.

