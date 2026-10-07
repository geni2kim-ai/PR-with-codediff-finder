# TextDiffChecker RSI / Backdata v2.4

Every accepted sensor run can become a case. Evaluation combines deterministic invariants, upper-review outcomes, author response, post-merge incidents and optional oracle data.

Keep per-axis scores (correctness, coverage, stability, performance, calibration, safety); do not collapse learning to a single opaque score. Low-scoring or repeatedly reproduced families are candidates for regression fixtures and improvement work, but RSI never self-approves production code or trusted standards.

Important family: `DIFF-FALSE-EXACT`. A valid opcode transform may still be a poor alignment. When the harness cannot prove the strong path, use `HEURISTIC` and escalate high-risk uses rather than representing the result as exact.
