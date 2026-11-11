# H04.11 / E69–E70: scope before plan selection

Compare the unchanged explicit-UNSUPPORTED cascade with a new strict full-text scope gate. Both use the same existing JSON and Python prompts, model, previews, temperature=0, max_output=400. Alternating pair order. Every live answer is freshly generated.

Seven authored cases: two canonical grammar cases with new numbers, one representable paraphrase intentionally outside the grammar, numeric threshold and conjunction with changed data, the exact known E68 OR counterexample, and a new OR paraphrase. This is an adaptive targeted pilot, not an independent representative holdout. SQLite supplies numeric oracles; gold plans and expected routes are never sent to the model.

The scope gate accepts two explicitly named flat CSVs, string-key inner/left joins, sum, optional one equality filter and explicit multiplicity/missing-value semantics, using fullmatch and schema checks. Unknown text routes directly to Python. No keyword blacklist and no fallback after a selected solver fails. Scope parsing does not certify model-generated plan semantics. The parsed specification is NOT used as the answer or substituted into live responses; evaluating local execution from that specification is a possible future separate hypothesis.

The narrow grammar accepts 2/7 new cases and 0/6 E65 plus 0/5 E67 cases. Those older tasks route to Python, including representable ones: potential loss of savings is a material limitation, not a parse success.

Acceptance on this pilot: scope solves all seven with no wrong submissions; compare real paired quality/cost against cascade. Record failures unchanged. Regardless of outcome, do not claim general correctness or activate production. Next action depends on observed failures or the grammar coverage cost.

Bounded live budget: 5000 effective tokens, at most 21 calls, 1200 per task; no automatic retries, expected preflight 18 calls. Same task budget for both cascade stages. Stop on unknown cost or remote stop. E46/E50 prior unknown ledgers remain untouched. Synthetic preflight uses gold answers and validates plumbing only. Freeze sources before paid calls, then retain raw request/response, CSVs, validation and ledger.
