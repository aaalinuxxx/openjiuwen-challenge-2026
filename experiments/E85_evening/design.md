# Evening 12 November: H04.20 and H04.21

Starting commit: 10fb48d. Rollback is available there. No solver changes for H04.20.

1. H04.20: one fresh full E77 mixed run (31 tasks, 26 solvable), real SDK, validated profile shared with production CLI: joins enabled, floors search/data/coding 300/700/800, concurrency 1. Budget 3000, at most 26 actual requests. Compare to historical E80 candidate (not a contemporaneous causal A/B). Acceptance: improve verified score over 63/78, retain all historical 21 solutions, no incorrect SOLVED or non-SOLVED answer files, intact protected inputs, all usage accounted, within budget. 26/26 is a target, not an assumption.
2. H04.21: new numeric join dev tasks, fractional values, duplicates, unmatched rows, empty results and paraphrases. Freeze oracle before live; keep separate unused holdout for morning. Maximum 4000 effective tokens for initial probe, explicit request cap. Select at most one root-cause correction from results; any followup gets a new frozen plan. Never retry until a favorable result.
3. Save every failed/offline/live attempt and usage. Stop new paid calls on unknown current spend, remote rejection or lost recording. Historical E46/E50 unknown ledgers remain unchanged.

Plan cap for evening: 10000 effective tokens (3000 mixed + 4000 new joins + 3000 correction); morning/final reserve is outside this cap. Additional hypotheses only after main checks and within remaining allowance/time.

Docker executable not available on this machine (ENOENT). Colleague handles packaging; Windows SDK execution is not a container certification. Production profile remains explicit --profile validated; legacy defaults unchanged.
