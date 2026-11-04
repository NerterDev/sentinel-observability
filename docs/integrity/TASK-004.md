# Relatório de Integridade de Engenharia — TASK-004

## Identificação
- **Tarefa:** TASK-004: Painel Web de Gestão SPA Estático Dark Mode (dashboard/)
- **Data:** 2026-11-04
- **Autoridade de Esquema:** `src/models.py` (`CurrentStatusPayload`, `HistoryPayload`, `StoreStatus`, `ForensicIncident`)
- **Caminho Canónico:** `dashboard/app.js` (com `dashboard/index.html` e `dashboard/styles.css`)

## Princípios Cumpridos
1. **Canonical Path First:** O cliente SPA Vanilla JS em `dashboard/app.js` é a única autoridade de apresentação frontend. Não existem frameworks pesadas ou dependências NPM desnecessárias, assegurando publicação pura e estática no GitHub Pages a custo zero.
2. **One Source of Truth:** Consumo exclusivo dos artefactos gerados em `dashboard/data/current_status.json`, `dashboard/data/history.json` e `dashboard/data/incidents/<id>.json`.
3. **Conformidade Estrita com o Contrato Universal de UX (.harness/invariants/ux_contract.yaml):**
   - **Os 7 Estados Existenciais:**
     - `EMPTY`: Mensagem orientadora quando não existem lojas configuradas.
     - `LOADING`: Skeletons visuais elegantes com pulso subtil sem layout shift.
     - `POPULATED`: Grid de cartões de loja de alto contraste com métricas de 30 dias (uptime, checkout success, TTFB médio) e série temporal SVG.
     - `ZERO_RESULTS`: Aviso explícito quando a combinação de filtros não encontra correspondência + botão "Limpar Filtros".
     - `PARTIAL_DEGRADED`: Banner de aviso não bloqueante caso a telemetria histórica falhe enquanto o status instantâneo funciona.
     - `ERROR`: Mensagem legível para humanos com botão de recuperação "Tentar Novamente" (Retry).
     - `SUCCESS_FEEDBACK`: Toasts de confirmação imediata (ex: "Dados atualizados com sucesso") com auto-fecho em 3-4 segundos.
   - **Hierarquia de Ações:** Estritamente 1 CTA primário por vista ("Atualizar Telemetria"). Ações secundárias contornadas (ghost/outline). Ações destrutivas isoladas.
   - **Previsibilidade Comportamental:** A tecla `Escape` fecha o modal forense imediatamente. O botão "Fechar" é idempotente (`Cancel is no-op`). Anel de foco visível (`:focus-visible`).
   - **Matemática Modular 4/8pt:** Todas as margens, paddings e gaps cumprem a escala `[0, 4, 8, 12, 16, 24, 32, 48, 64]`. Raios concêntricos (`R_filho = max(0, R_pai - padding)`).
   - **Design Tokens Canónicos:** Mapeamento integral dos tokens de `src/theme.py` em variáveis CSS nativas (`--surface: #0d1117`, `--action-primary: #238636`, etc.).
   - **Governança de Ícones:** Vetores SVG monocromáticos herdando `currentColor`, proibição absoluta de emojis em botões funcionais.

