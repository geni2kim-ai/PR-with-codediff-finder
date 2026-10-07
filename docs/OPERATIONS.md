# Operations / GitHub Binding

## Profiles
Native Copilot is advisory only. The harness profile owns machine schema, SHA freshness, escalation, check conclusions and merge gating.

## Triggers
Recommended: `opened`, `reopened`, `synchronize`, `ready_for_review`. Draft reviews may be advisory; final gate occurs when ready unless repository policy says otherwise.

## SHA binding
Every result binds `base_sha` and `reviewed_head_sha`. Before final post/gate, harness reads current head again. Mismatch => `STALE`; never reuse prior PASS as current.

Incremental review may inspect previous-head → current-head to reduce duplicate work, but final result must remain consistent with base → current-head risk.

## Gate mapping
Harness-derived conclusion:

| Condition | Check conclusion |
|---|---|
| stale/abandoned | cancelled |
| missing evidence/policy | action_required |
| blocker/major finding | failure |
| required ADVERSARIAL not yet completed | action_required |
| human review required but not confirmed | action_required |
| minor/nit only | neutral |
| clean + required authority reached | success |

Thus `analysis_status=PASS` does **not** imply `success`.

## Fork/privileged execution
Never execute untrusted fork/head code with secrets or privileged tokens. Split untrusted build/test from trusted metadata/commenting. `pull_request_target`-style privileged contexts must not check out and execute untrusted head code.

## Optional auto-fix
Disabled by default. If explicitly enabled: same-repo only, allowlisted paths, default max 3 files/50 lines/1 cycle; never governance/auth/security/payment/migration/dependency/CI/infra/public-contract/secrets/release paths. Fixer cannot approve. Required checks must actually rerun; never assume a bot push automatically triggers CI.


## Sensor execution
Run `tools/textdiff_adapter.py` before model review. Validate the output with `tools/validate_textdiff_evidence.py`. The adapter reads Git objects locally and emits metadata/digests rather than source bodies. A semantic validation failure is a harness failure, not a reviewer finding.

## Backdata closeout
After merge/reject/incident information is known, update the immutable case trail, run `evaluate_sensor_case.py`, validate the score, and route the case with `route_case.py`. Adversarial packets carry refs/digests; source material remains in the repository or an explicitly approved minimized fixture.
