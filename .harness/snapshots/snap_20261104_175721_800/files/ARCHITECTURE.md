# Architecture Proposal — Plataforma de observabilidade web

**Status:** PROPOSED — not yet human approved.

## Principle
This document is a proposal, not a statement of truth. The project Harness must distinguish facts from assumptions and hypotheses.

## Project idea
# DESCRIÇÃO DO PROJETO: PLATAFORMA DE OBSERVABILIDADE SINTÉTICA E FORENSE E-COMMERCE (NÍVEL TIER-S)

## 1. Visão Geral e Objetivo
Construir uma plataforma de observabilidade sintética ponta a ponta (E2E) e diagnóstico forense para lojas online WooCommerce/WordPress, com execução periódica automatizada e publicação num painel web interativo e estático (GitHub Pages), a custo zero de infraestrutura e sem qualquer impacto de desempenho nas lojas.

O sistema monitoriza múltiplos ambientes de alojamento heterogéneos:
- **Cloud Edge Gerida:** Rocket.net com camada Cloudflare Enterprise (Edge Caching, WAF, Turnstile/Desafios de Bot).
- **Servidores VPS:** Instalações Linux convencionais (Nginx/PHP-FPM/MariaDB).
- **Servidores Dedicados Bare-Metal:** Ambientes de alta performance com isolamento estrito de hardware.

O objetivo primordial é detetar instantaneamente quedas silenciosas de vendas e conversão causadas por falhas pós-clique que não derrubam o site (onde o HTTP responde 200, mas a compra é impossível), tais como:
1. Erros não tratados de JavaScript no navegador que bloqueiam o formulário de checkout.
2. Falhas assíncronas em endpoints críticos do WooCommerce (ex.: `/?wc-ajax=update_order_review` ou `checkout`).
3. Ausência de métodos de envio para compradores internacionais/EUA (`.woocommerce-no-shipping-available-html`).
4. Falha na injeção de iFrames ou scripts de gateways de pagamento (Stripe, PayPal, etc.).
5. Bloqueios acidentais por regras de firewall WAF ou desafios Cloudflare.

---

## 2. Garantia Estrita de Não-Interferência (Zero Footprint)
- **Zero Instrumentação no WordPress:** Não são instalados plugins, scripts PHP ou tarefas no `wp-cron`.
- **Zero Impacto de CPU/RAM nas Lojas:** A computação pesada (Chromium headless, renderização DOM, execução JS) ocorre fora dos servidores de produção, correndo nos runners do GitHub Actions alojados em datacenters nos EUA (Azure East/West US).
- **Sonda Externa Fidedigna:** O sistema comporta-se como um comprador real nos EUA navegando na loja a cada 30 minutos.

---

## 3. Arquitetura da Solução

```text
┌────────────────────────────────────────────────────────┐
│             GITHUB ACTIONS RUNNER (REGIÃO EUA)         │
│  (Execução agendada via Cron a cada 30 minutos)        │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. Leitura de Configurações (sites.json)         │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 2. Teste de Rede & TLS (TTFB, SSL, DNS)          │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 3. Sonda Sintética Playwright (Chromium US)      │  │
│  │    - Interceção de consola (pageerror / console) │  │
│  │    - Interceção de rede (wc-ajax >= 400)         │  │
│  │    - Validação de DOM (Carrinho -> Checkout)     │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │                            │
│           ┌───────────────┴───────────────┐            │
│           ▼                               ▼            │
│      [SUCESSO]                        [FALHA]          │
│  Métricas de latência,           Screenshot full-page, │
│  TTFB e Web Vitals               dump de erros JS/AJAX │
│           │                               │            │
│           └───────────────┬───────────────┘            │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 4. Persistência GitOps (JSON deslizante 30 dias) │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 5. Publicação Automática no GitHub Pages         │  │
│  │    (Dashboard Web SPA estático sem backend)      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 4. Requisitos Funcionais do Sistema

### 4.1. Motor de Sonda Sintética (Python + Playwright)
- Execução em Chromium com perfil de utilizador real nos EUA (`en-US`, timezone `America/New_York`, resolução 1440x900).
- Suporte a cabeçalho HTTP personalizado de bypass de WAF/Cloudflare (lido da secret `WAF_BYPASS_TOKEN`).
- **Intercetores Ativos:**
  - `pageerror`: captura todas as exceções não tratadas de JavaScript com mensagem, ficheiro e linha.
  - `console`: filtra e guarda mensagens de erro (`console.error`).
  - `response`: inspeciona respostas HTTP; sinaliza qualquer chamada a `wc-ajax` ou gateways com código $\ge 400$.
- **Fluxo do Cenário de Checkout:**
  1. Acede ao URL do produto e valida tempo de resposta e TTFB.
  2. Clica no seletor de adicionar ao carrinho e confirma a reação da interface.
  3. Navega para a página de checkout.
  4. Aguarda a montagem completa da tabela de revisão do pedido (`#order_review`).
  5. Verifica a ausência do seletor `.woocommerce-no-shipping-available-html` (bloqueio de frete).
  6. Valida a presença visível de recipientes de pagamento (Stripe Elements, botões PayPal, etc.).
  7. Se ocorrer falha ou timeout (teto de 25s por passo), captura screenshot em formato WebP/PNG e grava o extrato do DOM e logs de rede.

### 4.2. Persistência de Dados e Histórico (GitOps)
- Os resultados são consolidados em ficheiros JSON dentro do repositório:
  - `dashboard/data/current_status.json`: estado instantâneo de cada loja (`HEALTHY`, `DEGRADED`, `CRITICAL`), latências e último teste.
  - `dashboard/data/history.json`: série temporal dos últimos 30 dias (limpeza automática de registos mais antigos para manter o repositório leve).
  - `dashboard/data/incidents/`: registos individuais detalhados de cada falha técnica detetada.
  - `public/screenshots/`: imagens com evidência visual das quebras.

### 4.3. Painel Web de Gestão (Dashboard Estático - GitHub Pages)
- Interface Single Page Application (SPA) moderna em modo escuro (Dark Mode: tons ardósia/obsidiana, Tailwind CSS, ícones Lucide).
- **Cartões de Estado por Loja:** Identificação da loja, badge do tipo de infraestrutura (`Rocket.net / Cloudflare`, `Bare-Metal`, `VPS`), badge de saúde operacional, dias restantes do certificado SSL e latência média.
- **Gráficos e Indicadores:** Uptime dos últimos 30 dias, taxa de sucesso de checkout, tempo médio de carregamento.
- **Gaveta/Modal de Investigação Forense:**
  - Clique numa loja com falha abre o diagnóstico detalhado.
  - Visualizador do screenshot da quebra com zoom.
  - Terminal com destaque de sintaxe exibindo os erros exatos de JavaScript da consola do browser.
  - Lista de chamadas AJAX com erro HTTP (status, payload e endpoint).
  - Veredito da causa-raiz em português claro (ex.: *"Erro de JS impediu cálculo do checkout"* ou *"Nenhum método de envio disponível para os EUA"*).

---

## 5. Estrutura de Ficheiros Esperada

```text
.
├── .github/
│   └── workflows/
│       └── sentinel_engine.yml        # Workflow do GitHub Actions (Cron 30m + Deploy Pages)
├── config/
│   ├── sites.json                     # Lista de lojas, produtos, seletores e regras
│   └── thresholds.json                # Limiares de latência, SSL e timeouts
├── dashboard/                         # Código-fonte do Painel Web
│   ├── index.html                     # Interface SPA responsiva
│   ├── app.js                         # Lógica de renderização, gráficos e modais
│   ├── styles.css                     # Estilos customizados e tema escuro
│   └── data/                          # Dados atualizados automaticamente pelo runner
│       ├── current_status.json
│       ├── history.json
│       └── incidents/
├── public/
│   └── screenshots/                   # Capturas de ecrã das falhas detetadas
├── src/
│   ├── __init__.py
│   ├── models.py                      # Esquemas de dados Pydantic
│   ├── edge_inspector.py              # Verificação de SSL, DNS e TTFB
│   ├── browser_probe.py               # Motor Playwright com interceção forense
│   ├── forensic_recorder.py           # Gestão de histórico, screenshots e JSONs
│   └── orchestrator.py                # Execução central multi-site
├── requirements.txt                   # playwright, pydantic, httpx, python-dotenv
├── .env.example
└── README.md                          # Manual de instruções e configuração de Secrets
```

---

## 6. Critérios de Aceitação e Qualidade
1. **Implementação Completa:** Todo o código em Python, JavaScript, HTML e YAML deve ser totalmente funcional, sem funções vazias ou comentários de preenchimento posterior.
2. **Resiliência a Falhas:** Se uma loja estiver inacessível, o teste dessa loja deve registar a falha com screenshot e seguir para as restantes lojas sem abortar a execução global.
3. **Página Pública/Privada Operacional:** O GitHub Actions deve fazer o build e deploy para o GitHub Pages de forma atómica após cada bateria de testes.
4. **Documentação:** O ficheiro `README.md` deve explicar passo a passo como configurar o repositório, como adicionar novos sites em `sites.json`, como configurar o bypass de WAF na Cloudflare/Rocket.net e como ativar o GitHub Pages no repositório.

## Candidate architecture
The Architect should document components, interfaces, data flow, deployment, failure modes, and verification boundaries here.

## Alternatives
At least one alternative should be recorded whenever a structural decision is consequential.

## Assumptions
See `.harness/assumptions.yaml`. Do not silently promote assumptions to facts.

## Open questions
See `.harness/assumptions.yaml` and `.harness/architecture-options.yaml`.

## Architecture challenge
See `.harness/architecture-review.yaml`. The architecture is not approved until the challenge findings have been reviewed.

## Human decision
See `DECISIONS.md`.


## V6 Cost Control and Antigravity

Model selection is a human-controlled boundary. Context Optimizer and deterministic tooling reduce token consumption without selecting a model. Antigravity remains the execution environment; the Harness supplies contracts, task context, worktrees and evidence gates.
