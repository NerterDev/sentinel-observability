# 🚀 Guia de Início Rápido no Google Antigravity — Plataforma de observabilidade web

Gerado automaticamente pelo **AI Harness Architect 6.3**.

---

## 💡 Como funciona a "Conexão" com o Antigravity?
Não é necessário configurar servidores, portas de rede ou tokens complexos:
Apenas precisa de **abrir esta pasta no Google Antigravity** (`File -> Open Folder` ou `Ficheiro -> Abrir Pasta`).

Ao abrir a pasta no Antigravity, o editor deteta automaticamente:
1. As **Regras de Governança** no ficheiro `AGENTS.md` (o agente lê antes de tomar qualquer ação).
2. Os **Comandos Automáticos (Skills)** em `.agents/skills/` (comandos iniciados com `/`).

---

## 🎯 Passo a Passo para Começar a Desenvolver

### 1. Abrir o Chat do Agente
No Antigravity, abra o painel lateral do Chat onde conversa com a IA.

### 2. Primeiro Comando: Alinhamento Inicial
No chat da IA, envie:
```
/harness-bootstrap
```
*(Ou, se preferir, copie e cole o texto de `templates/antigravity_prompts/00_BOOTSTRAP.md`)*
👉 **O que a IA vai fazer:** Ela lê os ficheiros de governança e apresenta um resumo da prontidão do projeto. A IA **não altera nenhum código nesta etapa**.

### 3. Criar a Primeira Tarefa de Código
Diga ao agente o que deseja desenvolver usando o comando `/harness-plan`:
```
/harness-plan <descreva o que quer criar>
```
*Exemplo:* `/harness-plan Criar tela inicial com lista de espécies botânicas e busca`
👉 **O que a IA vai fazer:** Ela gera um Contrato de Tarefa em `tasks/` detalhando o que vai implementar, quais os ficheiros afetados e como será testado.

### 4. Implementação e Verificação
Quando estiver de acordo com o plano, envie:
```
/harness-implement
```
E quando a IA terminar de programar, envie:
```
/harness-verify
```
👉 **O que a IA vai fazer:** O agente executa os testes determinísticos e validações. Se algo falhar, use `/harness-repair` para ele corrigir a causa-raiz.

### 5. Concluir a Tarefa com Evidência
```
/harness-close
```
👉 **O que a IA vai fazer:** O agente sela o recibo de conclusão em `receipts/`.

---

## 🛠️ Resumo dos Comandos com Barra no Chat:
- `/harness-bootstrap` ➔ Inspecionar o projeto e verificar governança
- `/harness-plan` ➔ Planear uma nova tarefa antes de escrever código
- `/harness-implement` ➔ Implementar a tarefa aprovada de forma canônica
- `/harness-verify` ➔ Executar testes e verificar efeitos reais
- `/harness-repair` ➔ Diagnosticar e reparar falhas identificadas nos testes
- `/harness-close` ➔ Concluir a tarefa e selar o recibo de entrega
