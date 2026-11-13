# H04.29 output-floor pilot

Base production8861edf unchanged. Candidate is an experimental BudgetTracker subclass patched only into this benchmark. It first obtains the normal atomic reservation; if cap is below min(requested_cap,type_floor), records NOT_SENT and releases it before transport is even obtained. Zero cost and no request-count slot consumed. Thresholds fixed before live: math32,data64,coding128,search8,other32. Selection uses public task type only. Budget ledger, output execution, task order, models and prompts are otherwise unchanged. No larger cap or math solver change.

Same100 E105 tasks/83solvable/max246,seed2026111202,76known copies+24 previously observed authored cases. This is an adaptive known-workload pilot, not fresh holdout. Standard ROI/csv-roomy/C1 in both arms. Baseline first, floor second, budget500/max30HTTP each. Single fixed order, no repeated runs to select winners.

Acceptance fixed before live: at least one floor denial, fewer truncations, no increase in wrong SOLVED or input/accounting failures, and either higher total verified score or same score at lower actual cost. Every rejected/unattempted task remains in denominator. Local answers included equally. Report lost/gained solutions and exact floor denials; fewer truncations alone is not a win. A denial after an earlier paid call is not a free task: all earlier usage remains charged.

Unit tests and both noHTTP offline SDK controls before API. Cap sum1000 leaves campaign<=20899.5 versus proposed21000; campaign starts224HTTP/19899.5. This is internal allowance, not remaining account quota. Stop second arm on unknown expense, failed recording or remote rejection. Historical E46/E50 journals unchanged. No production promotion from a single pilot.
