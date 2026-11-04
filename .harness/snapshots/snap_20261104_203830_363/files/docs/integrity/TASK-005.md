# Relatório de Integridade de Engenharia — TASK-005

## Identificação
- **Tarefa:** TASK-005: Automação GitHub Actions e Publicação GitHub Pages (.github/workflows/sentinel_engine.yml)
- **Data:** 2026-11-04
- **Autoridade de Esquema:** `src/models.py`
- **Caminho Canónico:** `.github/workflows/sentinel_engine.yml` (com `README.md` e `.env.example`)

## Princípios Cumpridos
1. **Canonical Path First:** O workflow `.github/workflows/sentinel_engine.yml` é a única esteira de automação CI/CD do projeto. Não existem scripts secundários de deploy fora da infraestrutura canónica do GitHub Actions e GitHub Pages.
2. **One Source of Truth & Zero Redundância:** A configuração de lojas monitorizadas (`config/sites.json`) e limiares (`config/thresholds.json`) permanecem a única autoridade de entrada para o runner.
3. **Prevenção de Loops de CI (Anti-Loop Guarantee):** O passo de commit GitOps inclui a flag determinística `[skip ci]`, garantindo que os commits de atualização de telemetria não disparam novas execuções em cascata.
4. **Isolamento de Segredos e Princípio do Menor Privilégio:** Permissões do workflow são configuradas explicitamente (`contents: write`, `pages: write`, `id-token: write`). Segredos de WAF (`WAF_BYPASS_TOKEN`) são passados via GitHub Secrets sem exposição em logs.
5. **Zero-Footprint Constraint:** O runner executa remotamente na região dos EUA (`ubuntu-latest`), garantindo inspeção sintética a partir da mesma geografia dos clientes alvo sem consumir CPU/RAM ou instalar plugins/código PHP no WordPress das lojas.

