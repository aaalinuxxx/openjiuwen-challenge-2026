# H04.33: align math task reservation with the unchanged requested cap

Adaptive follow-up to H04.32, NOT a fresh holdout. Same24 tasks/22solvable/max66, calibrated/csv-roomy,C1,models/prompts unchanged. Reuse both E119 baseline reports with SHA256 and all original107 frozen input hashes checked before running. No duplicated baseline billing.

Only math admission changes: cumulative task ceiling becomes max(original task ceiling,already-accounted task cost + conservative input estimate/10 + requested output cap). Global ledger limit, requests limit, unknown-cost stop, and actual usage settlement remain unchanged. No new retries, no low first-pass caps, no answer-based routing. Requested math cap remains200. Global shortage can still reduce the actual cap.

Order: candidate800 then candidate2000. Acceptance: audit and integrity pass, zero wrong SOLVED, no score loss at either budget and gain at least once. This adaptive pilot is insufficient for broad claims. Do not integrate before separate regression.

Baseline:800=35/66,650.9tokens,13HTTP;2000=61/66,1637.1tokens,21HTTP. New trials counted separately.
