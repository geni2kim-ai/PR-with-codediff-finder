# R9B.4.1 Windows rehearsal — verifier PID producer/evaluator contract mismatch

- date: 2026-10-08
- returned package: `ym_r9b41_package_20261008.zip`
- returned ZIP SHA-256: `ad804acca310bd56fbde0f3314ef6f635abf939cfb55f15dcae73dfe899883fd`
- review baseline: `PR-with-codediff-finder v2.6 hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`
- Harness Full Validation: #153/#154 SUCCESS
- classification: `INTEGRATION_GAP / PRODUCER_CONSUMER_CONTRACT_DEFECT`
- severity: high
- disposition: `R9B41_WINDOWS_REHEARSAL_BLOCKED / R9C_BLOCKED`

## Observed

The R9B.4.1 Windows measurement itself reached `CAPTURE_READY`, but the first evaluator invocation returned:

`R9B4_DENIED / CAPTURE_VERIFIER_PID_INVALID`

The duplicate invocation returned the same result and no replay-ledger token was consumed.

The reason is a direct producer/evaluator schema mismatch:

Evaluator requires:
- `capture.verifier.pid == harness.server_pid`
- `completion.verifier_pid == harness.server_pid`

Issued producer `r9b4/src/VerifierServer.cs` emits neither field.

The Windows return confirms the omission in real produced artifacts.

## Impact

This blocks:
- first live evaluation;
- duplicate one-time replay consumption test;
- review-safe offline verification;
- several later cross-binding checks that occur after verifier PID validation.

The normal measurement capture itself is not invalidated, and the authority ceiling remains fail-closed:
`MEASURED_NOT_AUTHENTICATED / UNBOUND / NOT_AUTHORIZED / NONE`.

## Required correction

Create a narrow R9B.4.2 correction:

1. In `VerifierServer.cs`, emit:
   - `capture.verifier.pid = Process.GetCurrentProcess().Id`
   - `completion.verifier_pid = Process.GetCurrentProcess().Id`
2. Do not relax evaluator PID validation.
3. Add a producer/evaluator contract regression test that fails if the producer stops emitting either field.
4. Run clean-extract tests and completeness gates again.
5. Re-run Windows rehearsal from the corrected exact source:
   - normal measurement;
   - first live evaluation;
   - immediate same-ledger duplicate -> `RUN_TOKEN_ALREADY_CONSUMED`;
   - review-safe offline verification.
6. Preserve all already-passing cleanup, authority-ceiling, pin-negative, wrong-SID and privacy gates.

## Additional evidence note

The returned package contains `OUT_OF_BAND_ANCHOR_REQUIRED.txt` but no actual immutable external anchor reference for the review bundle.
Before independent/HUMAN review, publish the final review ZIP SHA-256 through a separate immutable channel and return that reference.

## Gate

Current state:

`R9B41_WINDOWS_REHEARSAL_BLOCKED_ON_VERIFIER_PID_CONTRACT`

R9C remains blocked.
