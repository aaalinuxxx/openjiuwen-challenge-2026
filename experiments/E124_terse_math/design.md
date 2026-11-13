# H04.35: append-only brevity guidance

Adaptive child of H04.34. H04.34 failed on budget2000:55 vs61 with1 incorrect answer; compact replacement prompt is rejected, no fresh/mixed runs for it. New variant preserves original math system prompt byte-for-byte as prefix and appends only: Keep code minimal: no comments, explanations, or unnecessary helper functions. Full user instruction, cap200, allocation and models unchanged. Longer prompt may slightly reduce actual cap.

Target800 then2000 compared with unchanged E119 baselines; require no score loss at either, improvement at least once, zero incorrect SOLVED or integrity/accounting failures. If passed: fresh baseline then candidate on the12 E122 tasks frozen before H04.34 outcomes, budget2000; require no lost tasks/no wrong SOLVED/no score loss. Then actual integrated SDK full E77 regression26/26 and78/78 before adoption. No cap tuning or retries.

This is adaptive variant development. The fresh12 tasks have never been sent to API as of preregistration. All failed variants remain in evidence.
