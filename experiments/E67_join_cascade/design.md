# E67/E68 — H04.10: live JSON → Python cascade

Hypothesis: using typed local join first and invoking Python only after explicit UNSUPPORTED can recover unsupported conditions while preserving duplicate-safe local execution on supported plans. Test the actual cascade, not a composition of old answers.

Five new task variants: duplicate inner join, left sum, numeric threshold, two simultaneous filters, and left join with an OR condition preserving unmatched rows. Two are expressible in the fixed JSON grammar; three are not. All five expected answers checked independently with SQLite TEXT keys. Gold plans are fixture metadata only and are never used to choose the live route.

Baseline: direct multi_csv Python. Candidate: solve_join_plan_task; fallback only if status is UNKNOWN with the explicit UNSUPPORTED marker. Invalid JSON, execution failure, budget denial and uncertain usage do NOT trigger fallback. A valid but semantically wrong plan can still be returned as SOLVED; this study does not assume the schema proves question semantics.

The same bridge, context/task id and BudgetTracker are used across both calls. Both usage records count. Full suite 128 tests, including no fallback on malformed plans, accounting both calls, global/task/count admission, uncertain first/second usage. These budget/failure tests use synthetic transports, not real API quota exhaustion.

Live settings: real openJiuwen/NeuralDeep qwen3.6-35b-a3b-noreason, temperature 0, max output 400 per call, sequential alternating arm order. Global experiment budget 4000 effective tokens, at most 15 calls (expected 13: 5 direct, 8 cascade). Each task has 1200; the first call reduces the remainder available for fallback. No automatic retries. Unknown usage stops new requests. Old E46/E50 ledgers kept unchanged.

Record phase json_plan/python on every actual request, raw payload/response without credentials, per-task result and summed usage, input hashes, answer.txt. Check all answers against the oracle, CSV immutability and absence of unexpected files.

Metrics: solved/5, supported/2 and outside-plan/3, wrong answers, actual fallback count, all-stage costs. Unsupported is not a solution. Candidate remains experimental; no default-dispatch integration. Existing wide challenge 9/19 remains historical.

Preflight uses gold plans or synthetic constant Python output and validates the orchestration, not generation quality. First freeze sources, fixtures and preflight; then run live once with an exclusive start marker.
