# Antigravity Integration — AI Harness Architect v6.3

This project is **Google Antigravity-first**. Antigravity is the development/execution environment; the Harness is the engineering governance, context, state, verification and receipt layer.

## Model authority

The user selects the model manually in Antigravity. The Harness MUST NOT automatically choose, switch, escalate, downgrade or retry with another model.

The Harness may classify task complexity and recommend a capability level, but this is advisory only.

## Standard startup

1. Open this project folder in Antigravity.
2. Confirm the workspace root is this folder.
3. Select the model manually.
4. Read `ANTIGRAVITY_START_HERE.md`.
5. Run `/harness-bootstrap`.
6. Review the architecture and unknowns.
7. Define the first task with `/harness-plan`.
8. Implement with `/harness-implement`.
9. Verify with `/harness-verify`.
10. Repair with `/harness-repair` when needed.
11. Close with `/harness-close` only after evidence passes.

## Workspace skills

The generated project contains `.agents/skills/` with reusable Harness skills. These are workspace-scoped and should be committed with the project when appropriate.

## Prompt fallback

If a skill is not available in the current Antigravity surface, use the equivalent prompt under `templates/antigravity_prompts/`.

## Completion rule

Implementation is not completion. Completion requires deterministic evidence and, where applicable, runtime/integration/observable-effect verification and a valid receipt.
