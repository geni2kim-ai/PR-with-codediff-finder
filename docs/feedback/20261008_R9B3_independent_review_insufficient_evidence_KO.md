# R9B.3 independent review — evidence closure insufficient for CLOSED label

- date: 2026-10-08
- review target: R9B.3 v2.6 independent/HUMAN review bundle
- applied review baseline: `hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`
- Harness Full Validation: #153 SUCCESS, #154 SUCCESS
- disposition: `INSUFFICIENT_EVIDENCE / R9C_BLOCKED`
- classification: `EVIDENCE_GAP + RUN_BINDING_GAP + CLEANUP_VERIFICATION_GAP`

## High findings adopted

### H1 — cleanup path not proven

The returned N6 evidence shows a self-terminating failure path (server exit 1 / client exit 0). It does not exercise
the forced timeout/kill path.

`cleanup_attempted=true` is not itself proof that bounded termination succeeded. Future evidence must include
target process IDs, timeout/kill path execution, bounded wait result, before/after process existence, and child-tree
residual checks.

### H2 — distributable binding set is not independently replayable

The review bundle contains masked capture/registry/run-context artifacts whose hashes differ from the original
raw bindings. The transformation lineage is not sufficient to reconstruct a runnable, self-consistent review set.

Remediation:
- produce a review-safe re-bound artifact set whose masked bytes have their own complete SHA bindings;
- include a transformation receipt that lists changed fields and pre/post hashes;
- include an out-of-band digest/signature reference when available;
- do not describe the inner REVIEW_BINDINGS.json alone as an external trust anchor.

### H3 — stale rejection is not one-time replay prevention

The expired-original test proves freshness-window rejection. It does not prove nonce/run-id consumption or
single-use replay prevention.

Remediation:
- either implement verifier-side state/ledger consumption for run_id/nonce and test duplicate evaluation/reuse; or
- explicitly downgrade the claim to `FRESHNESS_BOUND_MEASUREMENT` and state that same-window repeated evaluation
  is permitted and not considered replay prevention.

## Medium findings adopted

### M1 — literal status fields are not measured evidence

Fields such as `registry_created_by_measurement_runner=false`, `explicit_acl=true`, and similar capability/status
flags must either be derived from an independently checkable operation/result or clearly classified as configuration
claims rather than evidence.

### M2 — operator pins remain rehearsal provenance

Operator-supplied pin material is useful against post-selection mutation but is not an independent trust anchor.
This residual must remain explicit until a protected/non-exportable credential or external approval root exists.

### M3 — missing cross-bindings

The evaluator must additionally validate at least:
- completion status;
- preflight SHA binding across run-context and harness;
- run_id across capture/pipe/completion as applicable;
- build receipt digest;
- harness-launched client PID against the captured client PID;
- client process creation time inside the run window.

### M4 — server PS1 TOCTOU/type reuse

The PowerShell server itself is only preflight-pinned before `powershell.exe -File` execution. If retained, use a
verified immutable copy/temp or other execution mechanism that binds the executed bytes. Also fail closed if the
capture type is already loaded rather than silently reusing it.

### M5 — negative evidence completeness

Future Windows returns should include:
- all required negative cases, including the former N4a label if referenced;
- exitcode/stdout/stderr or equivalent for N1-N3;
- explicit server/client not-started evidence on preflight rejection;
- N6 server/client stdout/stderr and residual-process check;
- review-harness commit/run evidence when used to justify the review baseline.

## Label correction

Do not use `R9B3_TECHNICAL_EVIDENCE_CLOSED`.

Current maximum label:

`R9B3_WINDOWS_REHEARSAL_PASS_CANDIDATE_WITH_OPEN_EVIDENCE_GAPS`

Security ceiling remains:

`MEASURED_NOT_AUTHENTICATED / stable_node_id=UNBOUND / NOT_AUTHORIZED / authority_effect=NONE`

R9C remains blocked.
