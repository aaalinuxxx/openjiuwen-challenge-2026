# H04.23: ROI ranking versus reward-only under a shared constrained budget

100 tasks from E77: each of31 source tasks copied three times plus7 seeded samples. Random rewards1..5 are drawn independently of task type/difficulty (seed2026111201).84 solvable,16 impossible, maximum250 weighted points. Copies are pristine; changing task_id/reward does not change oracle or instructions. This is a load/allocation experiment on repeated known families, not100 independent new reasoning problems.

Compare two fresh sequential real-API runs: ROI first, reward-only second. Same source revision, models, prompts, validated settings, task-floor300/700/800, concurrency1, totalbudget3000 per arm, max100 calls per arm. ROI is unmodified production ordering. Reward-only descending reward, ties ascending task_id; this override exists only in benchmark subclass. Runtime scheduler defaults unchanged.

Primary metric: independently verified weighted score (max250), then lower effective cost at equal score. Secondary: verified tasks, incorrect SOLVED, non-SOLVED files, integrity, task types denied by budget, cost and latency. Count local solutions after budget exhaustion. Report actual reserved/unused budget and caps; selecting an order can change later caps and is part of allocation policy.

Accept a useful alternative only with higher verified score and no increase in incorrect answers or integrity/accounting failures. One seed and generation per task cannot establish robust superiority: winner is provisional; production ordering remains unchanged until independent confirmation. Never retry to pick a winner. Stop second arm on unknown spend/remote or recording errors in first. All failures preserved.

Two zero-budget rehearsals must have identical verified identities, scores and zero HTTP. Inputs/labels frozen before live. Six E87 holdout are NOT part of these100 tasks.

Status: DEFERRED before any scheduling API. E94 holdout found another truncation; repair/output-budget validation has priority. Fixture prepared, no ranking experiment executed yet.
