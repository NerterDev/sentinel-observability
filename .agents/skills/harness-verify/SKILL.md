---
name: harness-verify
description: Verify implementation, integration and observable effect across all affected boundaries.
---
# Harness Verify
1. Run deterministic tests.
2. Run deterministic UX audit (harness ux-audit) if user-facing code was modified.
3. Verify every affected architectural boundary.
4. Verify the consumer of each new capability.
5. Verify the final observable effect when the task crosses a boundary.
6. Record failures as evidence; never hide them with a bypass.
7. Completion requires evidence, not an assertion.
