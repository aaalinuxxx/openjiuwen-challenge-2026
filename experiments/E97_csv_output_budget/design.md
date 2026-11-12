# H04.16: multi-CSV hard cap600 with matching task reserve1000

Parent E94 first holdout5/6, one TRUNCATED at400. All other answers correct. Its raw response ignored the concise-code request and used many comments. The holdout is now observed dev; a followup cannot be called a new independent holdout success.

Change only two linked resource settings: multi-CSV requested cap400->600; data task minimum700->1000 to preserve headroom under the byte-based prompt estimate. Same model, prompt, parsing and scoring. A configurable cap defaults400; explicit csv-roomy profile enables600/1000. Default production validated remains400/700 until acceptance.

All six observed holdout tasks rerun once, budget3000,max6HTTP,concurrency1. Accept6/6, previous5 retained, no truncation/wrongSOLVED/nonSOLVED-files, intact inputs, all costs accounted. Compare to E94 as adaptive historical baseline, not randomized A/B. If accepted, run full E77 mixed budget3000/max26, require26/26 and no input/accounting errors before promotion. Stop on unknown spend or remote rejection.

Additional-session plan remains8500: E94 actual2028.4 plus at most3000 targeted plus3000 full=8028.4, remaining471.6 contingency. Scheduling H04.23 fixture is prepared but its API comparison deferred.
