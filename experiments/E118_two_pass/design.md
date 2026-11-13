# H04.32: short first attempts followed by selective retry

Before any API result, compare current calibrated/csv-roomy with an experimental two-pass wrapper. Fresh authored 24-task set, 22 solvable, max score 66. Familiar families, not organizer hidden data. Public metadata has no labels; references remain outside copied task roots.

Both arms use identical tasks, routing, model prompts, C1, and budget accounting. First pass candidate output caps: math64, search32 (unchanged), data96, coding128. After the entire first queue, retry at most once only TRUNCATED/FAILED tasks for which a requested cap was shortened. Solved, unknown, refusal, unknown usage and admission-only failures are never retried. Retry preserves the same task identity and cumulative usage. It runs only with all costs accounted and at least input reservation + min(original requested cap, twice first cap) remaining. No ground-truth feedback. Existing solver fallback is unchanged.

Run order fixed: baseline800, two_pass800, two_pass2000, baseline2000. Max50 calls/arm. No tuning after results; retain all outcomes. Dry-run SDK runs must make0 HTTP and preserve task inputs.

Acceptance: audited scores at both budgets must be no worse, with a strict improvement at least once; zero incorrect SOLVED, no input violations, unknown usage or budget exceedance. Otherwise keep production unchanged. Small sequential author-set pilot cannot establish statistical generality. Further validation required before default integration.

Arithmetic preflight caught an incorrect hand-count of coin combinations (10 instead of9) before model calls; initial failure log retained; final reference validated.

Before live runs, offline probes showed two intended local controls used unsupported delivery phrasing; changed only their delivery suffix to the existing recognized phrase. Initial dry runs and plans retained in preflight. Full unit discovery initially lacked USERPROFILE in this host launcher; rerun with the same bootstrap used by SDK experiments.
