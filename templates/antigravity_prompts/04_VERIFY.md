Verify the current task as a Harness task.

Do not rely on self-attestation.

Run:
1. deterministic tests
2. deterministic UX audit (harness ux-audit) if UI/frontend changed
3. engineering integrity checks
4. integration/boundary checks
5. runtime checks when applicable
6. observable-effect verification for every affected boundary

Trace the capability from implementation to consumer to final observable effect.
If anything fails, report the evidence and do not claim completion.
