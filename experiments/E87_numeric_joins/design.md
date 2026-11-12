# H04.21 numeric joins

10 new development tasks, 6 unused morning holdout tasks. Independent Decimal nested-loop oracle checked against manually supplied expected values before any model answer. Models see only four public task fields and CSV data. Names/amounts/task shapes are synthetic; not an external blind benchmark. Compare exact finite Decimal answers, no tolerant grading after results.

Dev: fractional products; many-to-many multiplicity; unmatched default; empty inner join; string keys with leading zeros; post-join predicate vs unmatched; rows beyond the first-three-row preview; negative amounts; round once using HALF_UP; weighted average with pairwise multiplicity.

Single baseline run using unchanged E86 solver/profile, budget4000, max10 calls. Goal 10/10 with no wrong SOLVED and all costs known. Errors direct ONE followup correction, frozen separately. Holdout remains unqueried until morning. Truncation vs admission-shrunk cap vs numeric mistakes are reported separately.
