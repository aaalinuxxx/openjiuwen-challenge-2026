# E65/E66 — H04.9: typed local join instead of generated Python

Hypothesis: representing an operation as a strict JSON plan and executing join locally preserves all matching pairs, fixing the live duplicate-loss failure E64. This does not prove that the model correctly translates every condition.

Six paired cases, frozen before live: one known E64 counterexample, four targeted variants (many-to-many/filter, left join duplicates, exact string keys, anti join with duplicate left rows), and one numeric-predicate case unsupported by the plan grammar. All six are solvable tasks; UNKNOWN on the last is an honest scope abstention, not a solution or impossibility proof.

Five gold plans are executed locally and compared with fixed answers. All six answers are independently checked using SQLite TEXT keys. Executor has 168 seeded differential comparisons against SQLite, exact decimal checks, rejection of invalid fields/files/numbers/empty keys, JSON duplicate-key checks and usage-preservation checks. Full suite: 121 tests.

The plan supports two different selected files, one exact nonempty string key per table, inner/left/anti joins, one optional post-join string-equality filter, sum of one numeric column or count of joined rows. Duplicate rows preserved. Missing right sum values contribute zero. Numeric thresholds, rounding, multiple filters, distinct and other aggregates are unsupported. Blank keys and malformed input produce UNKNOWN. Limit 1,000,000 generated pairs.

Both live arms: real openJiuwen and NeuralDeep qwen3.6-35b-a3b-noreason, temperature 0, max output 400, identical CSV files/instruction/preview data, sequential alternated arm order. Prompts differ to describe Python or the typed grammar; this compares architectures, not executor-only effects. No automatic retries, fallback or reasoning.

Separate budget 4000 effective tokens, maximum 12 API requests, task budget 1200. Unknown usage stops further requests. Old E46/E50 ledgers remain unchanged and their unknown usage is not claimed resolved.

Correctness requires the answer file to match the independent numeric oracle, no CSV modifications or unexpected files. Raw requests/responses, input copies, answers, usage and per-case status preserved. Report all-six accuracy, supported-five accuracy, wrong submitted answers, unsupported abstentions and total cost separately. Do not count UNKNOWN as correct solution.

Preflight uses gold JSON plans / constant-output Python to verify orchestration and delivery, not model quality. Negative schema controls and differential tests are offline. Candidate stays experimental, not enabled in production. Wide challenge remains historical 9/19.
