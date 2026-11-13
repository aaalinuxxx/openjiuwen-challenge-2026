# H04.30 ranking x admission interaction

Two measured ROI arms from E113 reused without spending API again. All386 frozen files (solver/model settings, public100-task fixture, labels, old benchmark and floor) match current bytes, reports fixed by SHA256. New live arms: calibrated+no-floor then calibrated+floor, budget500/max30HTTP/C1/csv-roomy each. Four-arm comparison is assembled sequentially, not simultaneous randomized factorial trial. Reused E113 results remain immutable. No new oracle/threshold fitting.

Calibration remains E92 medians math19,search19.3,data107.65,coding100.9. Changes only ROI ordering; original expected_cost remains the allocation estimate. Same fixed floors32/64/128/8. Full100E105 tasks/83solvable/max246 with all omissions counted. Known repeated families, not independent holdout.

Before live: all four wrapper variants run offline, match local solved IDs/49points, ROI order exactly matches E113; calibrated order exactly matches E107 calibrated offline order; expected_cost/reward identical for every ranked task. No production code changes.

Acceptance for combination: its verified score must be >= each of three alternatives, > original ROI/no-floor, with no increased incorrect SOLVED/integrity/accounting failure. Report effect of floor separately under ROI and calibrated ranking; report interaction as difference of score differences, descriptive only without uncertainty claim. Tie in score breaks by lower actual cost. Any smaller improvement or reversal is retained, not rerun. Before any production promotion, separate integration and full regression required.

User clarified there is no overall spending ceiling. Prior21000 was an internal plan, not service quota. Current continuation still uses at most1000 NEW tokens because matching500-arm budget is experimental control. Previous campaign239HTTP/20623.8 remains recorded; new calls never include reused E113 expense a second time.
