# R9B.2 adversarial review — trust/evidence/package hardening findings

- date: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- target: Agent OTP / Synapse R9B.2
- disposition: `R9B2_REHEARSAL_ONLY / DO_NOT_PROMOTE / R9B3_REMEDIATION_REQUIRED`

## Independently reconfirmed findings

### 1. PIN_IS_NOT_EXTERNAL_TRUST_ANCHOR — HIGH

R9B.2 provisions the registry and its pin from the same local step and the measurement runner only verifies the
registry against the supplied pin file. A subject-selected registry+matching pin pair can therefore be internally
consistent without being independently approved.

Remediation: require an **external expected registry SHA-256 literal/input** at measurement time. Provisioning must
not overwrite existing registry output and must hash the actual mediator executable as well as cross-check the build
receipt.

### 2. VERIFY_USE_AND_MEASUREMENT_CODE_PINNING_GAP — HIGH

The runner parses registry/build/pin and then separately re-reads/hash-checks files. R6 evidence producer
`invoke_r6_capture_server.ps1` and `R6NamedPipeCapture.cs` are loaded from disk without independent expected
hash pins.

Remediation:
- hash and parse the same registry bytes;
- require external expected SHA values for registry, mediator, server script and C# capture source;
- have the R6 server verify the exact C# source SHA before `Add-Type`;
- preserve a residual statement that on-disk executable SHA is not a loaded-image hash.

### 3. RUN_BINDING_AND_REPLAY_GAP — HIGH

The R9B.2 evaluator does not consume the measurement harness summary or server completion and does not validate
pipe/session/run/freshness binding. Several success labels are constants rather than evidence-derived fields.

Remediation: introduce a run context with nonce/run-id/session/pipe/time window and cross-check capture, completion,
harness summary, registry/build hashes and evaluator time. Client sends only the run nonce, never an identity claim.

### 4. REVIEW_GATE_UNSATISFIED — HIGH

CodeDiff remains degraded: `trusted_for_gate=false`, required level ADVERSARIAL, achieved SENSOR. Missing upstream
TextDiff asset/snapshot coverage prevents promotion.

Remediation: keep the package explicitly blocked from adoption. Snapshot validation must report missing pinned files
rather than `all_pinned_sha_checks_pass=true`.

### 5. STALE_PACKAGE_INTEGRITY_METADATA — MEDIUM

`candidate_repo/MANIFEST.sha256` is stale (124 entries, no R9B.2 files) and `candidate_repo/EVIDENCE.json`
describes the old R6 24-test state.

Remediation: regenerate the candidate manifest and replace EVIDENCE with the current cycle evidence model and actual
test counts.

### 6. PRIVACY_SEAL_SID_AND_COMMITMENT_GAP — MEDIUM

The distributable privacy seal does not natively scan SID patterns and emits unsalted SHA commitments of low-entropy
host identifiers.

Remediation:
- add default SID regex scanning;
- remove literal commitments from distributable seal output;
- keep any source material local-only;
- stop printing raw output paths from the R6 server.

### 7. POWERSHELL_AUTOMATIC_VARIABLE_LINT_GAP — MEDIUM

`run_r9b2_measurement.ps1` assigns `$matches`, colliding case-insensitively with automatic variable `$Matches`.
The linter only checks function parameter names.

Remediation: rename the variable and extend lint to ordinary assignments.

### 8. HARNESS_FAILURE_CLEANUP_AND_PATH_RESOLUTION_GAP — MEDIUM

Failure before the success block can leave server/client processes alive and omit diagnostic artifacts. Direct
`[IO.Path]::GetFullPath(".\x")` uses process CWD semantics rather than PowerShell provider current location.

Remediation:
- bounded kill/wait in finally for both children;
- always persist failure evidence/stdout/stderr/exit state;
- resolve operator paths through PowerShell provider-aware APIs.

### 9. PIPE_PROCESS_INSTANCE_BINDING_LIMITATION — MEDIUM

The R6 capture opens the client process only after request read and only rechecks creation/path on the same process
handle. The capture should re-check the pipe client PID around process evidence. On-disk SHA must not be represented
as a loaded-image hash.

Remediation: capture pipe PID immediately after connect, open the handle, then re-check
`GetNamedPipeClientProcessId` before completion and require equality. Record explicit hash semantics and residual
loaded-image limitation.

## Additional hardening

- evaluator always writes a typed deny result for malformed JSON/type errors and removes stale output first;
- PowerShell/Python comparisons use the same lowercase SHA and strict SID grammar;
- privacy/masking lineage receives the current R9B3 schema label;
- protect future stage aliases with wildcard security paths instead of enumerating each R9x directory;
- current package evidence should be curated/sanitized instead of carrying unrelated prep-environment tracebacks.

## Gate

R9B.2 may remain historical rehearsal evidence only.

The next candidate must not claim authentication, stable node identity, G1/F2, or runtime authority.

R9B.3 target ceiling remains:

`MEASURED_NOT_AUTHENTICATED / stable_node_id=UNBOUND / NOT_AUTHORIZED / authority_effect=NONE`
