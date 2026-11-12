# H04.18 / E83–E84: real API confirmation after restoring Windows access

Baseline is colleague commit 892223f45b9675e4ddd83039a152e64e6fe4a898; candidate uses the shared disposable CSV executor restored from the earlier cloud implementation. The unpublished cloud commit fb847f9 is not present on main or this disk; this is a separately frozen restoration, not a claim that its artifacts were imported.

Both arms: 13 E77 data tasks (12 solvable), original external labels, experimental_joins=True, minimum task budget700, total budget3000, maximum6 HTTP attempts, concurrency1. Baseline then candidate, same model35b-noreason and hard output caps200/400. Combined ceiling6000 effective tokens/12 HTTP attempts. No paid retries or post-hoc changes. New unknown cost, remote stop, recording error or worker failure stops the second arm. A one-time marker prevents repeated live runs.

The intervention is shared execution on CSV copies, strict single-line stdout/file agreement, file extraction before cleanup, no publication after crash/mutation/unexpected files, and a prompt explaining that the harness writes the final answer. Temporary cwd is not an OS security sandbox. Old answer.txt is neither input nor deleted. No answer is accepted merely because it is a bare numeric Python expression.

Acceptance: more externally verified solutions without losing baseline solutions or introducing unverified answer files/input changes; complete accounting. Known adaptive replay, not a blind holdout or full mixed-budget score. Model and task grammar unchanged. Prompt changes are part of this intervention.

Preflight:168 unittest methods passed including real openJiuwen SDK; the new shared test covers14 execution cases on each solver (28 subcases) plus a separate timeout test. The initial restoration had a CRLF splice error; it was corrected before freeze/API and the failing log is retained. Earlier cloud test counts used a different test-method layout.

Default command performs a zero-budget SDK rehearsal (six local solutions per arm, zero HTTP). --replay executes six stored E80 programs with zero new tokens, explicitly not new model evidence. --live runs both fresh API arms and stores raw requests/responses, ledgers, progress, task artifacts, independent grades and process logs. Sources, inputs, labels and old E46/E50 ledgers are frozen by hashes.
