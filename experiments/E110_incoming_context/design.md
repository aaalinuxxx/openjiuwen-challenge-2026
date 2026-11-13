# H04.27 matched incoming-context test

Baseline a3372e4, no other solver/profile/ranking/cap changes. Existing forward frontier is exhausted before incoming neighbors; incoming cards retain original facts, not invented reversed relations. Depth counts traversed edges in either direction, record/UTF8-byte limits unchanged. Retrieval is a bounded priority heuristic, not a guarantee of finding all short paths. include_incoming=False is byte-for-byte equal to old helper on all8 fixtures (context_audit.json).

Eight tasks: one observed E107 inverse failure; two new authored solvable inverse cases (employment, inverse then outgoing employer/city); one new ambiguous inverse case; four existing controls (custodian, exact product name, conflict, local three-hop). Six solvable/two impossible. Labels fixed before live and never copied into solver-visible task metadata. Small authored targeted validation, not external contest holdout.

Acceptance: incoming solves6/6 with correct abstention on both impossible cases, no incorrect SOLVED/truncation/integrity/accounting failures, all baseline solutions retained, strictly more inverse cases solved than forward. Record actual cost and added context. No fitting on paid responses, no retries to select results. Forward first, incoming second; single fixed order is a limitation.

199 unit tests, context equivalence audit and both zero-budget SDK runs before live. Each arm600 effective tokens/max10calls, total<=1200; prior campaign19659.8 means ceiling20859.8 within21000 proposal. These are internal spending limits, not account quota. Stop if unknown usage or recording/network rejection.
