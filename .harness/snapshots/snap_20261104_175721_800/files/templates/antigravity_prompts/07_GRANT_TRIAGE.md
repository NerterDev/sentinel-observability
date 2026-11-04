Execute Grant Ingestion & Eligibility Triage under the Harness Contract.

1. Review the startup's ground truth in `docs/startup_profile.yaml`.
2. Ingest the official regulatory bases (convocatória / bases reguladoras DOG/BOE/EU) into `docs/grant_opportunity.yaml`.
3. Run deterministic eligibility verification: `harness grants-audit .`
4. If any blocking failure is reported (DEBT_EXISTS, AGE_EXCEEDED, TRL_TOO_LOW, DNSH_VIOLATION, etc.), HALT and document the non-compliance.
5. If eligible or conditionally eligible with mitigation, produce `docs/eligibility_matrix.yaml` and draft the proposal structured strictly around the official scoring rubric and work packages.
