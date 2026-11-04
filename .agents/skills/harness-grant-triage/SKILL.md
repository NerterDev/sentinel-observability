---
name: harness-grant-triage
description: Audit startup eligibility and ingest regulatory bases (DOG/BOE/EU) before drafting grant proposals.
---
# Harness Grant Triage
1. Read docs/startup_profile.yaml to verify the startup's ground truth (tax, geography, TRL, de minimis).
2. Read the official regulatory bases (convocatória / bases reguladoras).
3. Run deterministic audit: `harness grants-audit .`
4. Do not draft a proposal if any blocking gate fails.
5. If eligible, structure the proposal adhering strictly to official scoring criteria and page limits.
