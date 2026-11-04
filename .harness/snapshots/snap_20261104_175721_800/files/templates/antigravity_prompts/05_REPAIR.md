A Harness verification failed. Repair it from evidence.

First classify the failure (CODE, TEST, CONTRACT, UX_CONTRACT, etc.) and locate root cause.
Trace the canonical path before modifying code.
Do not add a bypass, shadow configuration, wrapper, fallback or invented interface merely to make the check pass.
Apply the smallest correct repair, then rerun the relevant verification.
