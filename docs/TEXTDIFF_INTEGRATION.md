# TextDiff Integration v2.4

TextDiffChecker v1.4.6 is vendored with a harness API that adds algorithm provenance and conservative quality classification while preserving original API behavior.

Quality classes:
- `PROVEN_EXACT`: path satisfies the harness exactness rule;
- `HEURISTIC`: valid transform, but global optimality is not established;
- `APPROXIMATE`: explicit coarse/fallback behavior;
- `NOT_APPLICABLE`: non-text/skipped path.

The historical `DIFF-FALSE-EXACT` regression demonstrates why `approx=false` is not enough: banded Myers can return a valid but non-optimal alignment. The harness therefore records the actual algorithm path and classifies that path conservatively.

v2.4 also keeps `diff_texts_with_trace()` behavior aligned with `diff_texts_with_opcodes()` for findings/detail/opcodes and final cancellation checks.
