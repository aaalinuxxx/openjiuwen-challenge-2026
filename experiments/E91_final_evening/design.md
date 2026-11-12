# Final evening mixed regression and H04.19 diagnostics

Current paid evening total before this run:1896.6+3568.1+1767.5=7232.2. Final maximum2700, so planned total at most9932.2, below evening10000. At most26 calls. Same31 E77 tasks,26solvable, profile validated, concurrency1. This is a known/adaptive regression, not independent holdout.

Production differences from E86: concise multi-CSV system prompt (H04.22) and factual attempted-model metadata (H04.19). Metadata has no effect on prompts, routing, budget or execution. Historical comparison E86; acceptance all26solvable verified, previous25 retained, all protected files intact, no wrong SOLVED/non-SOLVED answer files, all cost known. Total budget2700 rather than3000 is explicit; compare actual request caps and ranking, do not claim matched-budget causal A/B.

H04.22 selected pilot:5/5, two truncations resolved, all3 prior correct controls preserved.1767.5tokens/5HTTP. Actual final weighted-average cap shrank to327 due remaining task budget (baseline400); therefore not fully matched-cap comparison. No claim that all10 E87 tasks were rerun with new prompt. Holdout6 tasks remain unused.

H04.19: replay real E86 truncation using fixture transport (zero HTTP), known-usage malformed response, unknown timeout, budget denial, local-only answer. All metadata must reflect last actual transport model, or empty if no transport call. Full unit regression and fresh final API validate integration.
