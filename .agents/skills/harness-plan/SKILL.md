---
name: harness-plan
description: Plan one implementation task under the Harness contract before changing code.
---
# Harness Plan
1. Read the task objective.
2. Locate the canonical implementation path and source of truth.
3. Identify affected boundaries and dependencies.
4. If task touches UI, CLI or user interfaces, enforce UX Contract (.harness/invariants/ux_contract.yaml) for the 7 existential states, single primary action, predictability, and design tokens.
5. Decide whether data trace, schema validation, integrity and effect verification are required.
6. Produce a minimal Task Contract with done_when and verification evidence.
7. Do not implement until the task plan is explicit.
