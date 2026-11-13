# H04.34: concise math code

Only math system prompt changes; full task instruction, model, temperature, requested output cap200, ranking, allocation, and global budget remain unchanged. No retries or H04.33 reservation expansion. Input length changes slightly, so the existing conservative reservation can yield different ACTUAL caps: this is part of the prompt change, not a matched-actual-cap study.

Targeted replay: same24 E118 tasks, budgets800 and2000. Reuse both E119 baselines only after verifying107 frozen inputs and report SHA256. Target acceptance: no lower score at either budget, improvement on at least one, zero incorrect SOLVED and input/accounting failures.

Fresh12-task suite created and frozen before candidate API results:10solvable/max27, two impossibility controls, references cross-checked with independent methods. Order after successful replay: fresh baseline then compact at2000 each. Acceptance: no lost correct tasks, no wrong SOLVED, score no worse; positive target gain must persist as quality/cost evidence. These are new author-generated instances of familiar families, not organizer hidden data.

Then full31-task E77 mixed regression, budget3000: require26/26 and78/78, no lost tasks or wrong SOLVED, no truncation, integrity/accounting pass. Only after all gates consider production integration, retaining a frozen original baseline prompt for experiment replay. No parameter tuning during these runs.

User-supplied chat clarification:100000 tokens is indicative; actual deployment budget may be smaller or larger. Runtime already accepts --budget, BUDGET, TOKEN_BUDGET; default100000 is not a guaranteed quota. Optimize score across budgets; exact local solvers remain useful.
