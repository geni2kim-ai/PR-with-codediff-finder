# Local Review Orchestration v2.4

## Stage independence

- L1 receives no previous-review conclusion.
- L2 receives no L1 result/ref/digest and must run in a fresh context.
- Adversarial review is the only model stage allowed bounded L1/L2 result refs/digests because its job includes adjudicating disagreement.
- Human remains the final authority for governance/hard-risk floors.

## Cycle states

`WAITING_L1`, `WAITING_L2`, `ADVERSARIAL_REQUIRED`, `HUMAN_REQUIRED`, `COMPLETE`, `BLOCKED`, `STALE`.

`PASS` is an analysis verdict, not permission to merge. If required authority is not achieved, the check conclusion is `action_required`. In SHADOW, GitHub preview rendering is always neutral.

## Freshness and worktree

The harness requires a clean tracked/untracked worktree at start except for the supplied evidence/output location. It re-reads HEAD and the worktree after review. A new commit produces `STALE`; reviewer-created uncommitted mutation produces `BLOCKED`.

## Failure handling

Reviewer timeout, process exit, invalid JSON, schema/provenance failure, unsafe output or output-cap violation creates `review-failure.json`, a `REVIEW_FAILED` event and a terminal BLOCKED cycle. `--retry` creates a new immutable `attempt-NNNN` directory instead of overwriting the failed attempt.
