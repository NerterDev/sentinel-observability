# Harness Operating Rules

You are operating inside an AI Harness.

## Mandatory startup

1. Read `PROJECT.md`.
2. Read `ARCHITECTURE.md`.
3. Read `.harness/contract.yaml`.
4. Read `.harness/policy.yaml`.
5. Read `.harness/verification.yaml`.
6. Read `.harness/state.json`.
7. Read `.harness/invariants/ux_contract.yaml` (when modifying UI, CLI or interfaces).
8. Inspect the relevant project map before changing code.

## Execution rules

- Do not invent requirements.
- Do not silently expand scope.
- Preserve existing behavior unless the contract explicitly changes it.
- Prefer deterministic checks before subjective judgment.
- Never declare completion without evidence.
- Classify failures before retrying.
- Respect protected paths and approval gates.
- Record meaningful decisions in `DECISIONS.md`.
- Update `.harness/state.json` when project state materially changes.

## Session Continuity & Turn-by-Turn Persistence

- At the start of any conversation turn, silently inspect `.harness/state.json` and `tasks/` to identify unresolved tasks and active context.
- When resuming a project (e.g. via Project Manager), anchor your response to the current state without requiring the user to restate previous context.
- Before concluding any turn that mutates files, architecture or state, persist the progress atomically into `.harness/state.json`.

## Universal Time Machine & Rollback Protection

- The Harness Time Machine (`harness snapshot` / `harness rollback`) is UNIVERSAL and mandatory across ALL projects managed by the Harness (WordPress, plugins, WooCommerce, mobile, web, desktop, backend, CLI, automation scripts).
- An atomic pre-mutation snapshot MUST be captured before executing tasks or mutating files.
- In case of regression, failure, or user request to return to a previous version, use `harness rollback` to deterministically restore all or specific files.

## Universal UX Contract Compliance

- Strictly obey `.harness/invariants/ux_contract.yaml` on all user-facing interfaces:
  - Implement the 7 Existential States (EMPTY, LOADING, POPULATED, ZERO_RESULTS, PARTIAL_DEGRADED, ERROR with recovery, SUCCESS_FEEDBACK).
  - Maintain Action Hierarchy: strictly 1 Primary CTA per view, destructive actions isolated in 2 steps.
  - Enforce Behavioral Predictability: Esc dismisses popups/modals, Cancel is strictly no-op.
  - Use modular 4/8pt spacing, concentric border radius, and monochrome icons with `currentColor`.
  - Axiom: "Implementação tecnicamente válida, UX contratualmente inválida" — UI code failing UX invariants is rejected.

## Completion rule

A task is complete only when the task's `done_when` conditions have evidence.

The final response should identify:
- what changed
- what was verified
- remaining risks
- files affected

## Failure classes

- ENVIRONMENT
- DEPENDENCY
- CODE
- TEST
- CONTRACT
- UX_CONTRACT
- PERMISSION
- EXTERNAL_SERVICE
- UNKNOWN

Retry only when the failure is plausibly transient or when the retry changes the state.

