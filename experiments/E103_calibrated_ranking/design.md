# H04.24: empirical type cost for ranking only

Parent E102: ROI score109,reward-only score105; reward-only is not a reliable improvement. Empirical costs from PRIOR E92, not fitted to E102: median math19,search19.3,data107.65,coding100.9. Prior estimator ranks data cheaper than math although observed generation costs are opposite.

Replace only ranking denominator with frozen type median, keep original p_solv and reward. Preserve original expected_cost in each task item, so admission/reservation calculations are unchanged; do NOT reduce math request allowance along with ranking estimate. Production scheduler remains untouched: subclass only. Known100-task workload, adaptive diagnostic, no claim of blind generalization.

Budget900,max100 requests,concurrency1,csv-roomy profile. This is LOWER than both E1021000 arms due remaining8500 session allowance. Accept as a promising pilot if verified score>both baselines, incorrect SOLVED0, intact inputs and known usage within900. Unequal budgets and one seed prevent a clean causal efficiency estimate. Do not promote production from this single workload. Next independent seed/holdout needed.

Before live require zero-budget25 solutions/75points and independent check that all expected_cost/reward/task identities match original ROI ranking, only order/roi changes. Remaining allowance before this run 962.6; maximum900.
