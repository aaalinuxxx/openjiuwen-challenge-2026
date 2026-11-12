# H04.22: concise generated code at unchanged cap

Parent H04.20/H04.21: two actual truncations at400; response bodies use extensive comments. Only change: append a concise-code instruction to multi-CSV system prompt. No arithmetic hint, join grammar, model, hard cap, evaluator or task-budget floor changes. Production single-CSV path unchanged.

Preselected tasks: both failures (filter_after_pairing and pilot_extra_numeric_control), duplicate_pairs, round_once, weighted_average. Five calls maximum,2000 effective tokens. Acceptance:5/5, no loss of three previously verified controls, no truncation, no wrong SOLVED, all cost known. Historical comparison of selected tasks is adaptive and not statistical proof. If passes, one full mixed regression; no repeated attempts to select lucky output. Six E87 holdout remain unused.
