# R9B.3 v2.6 review — negative-evidence coverage gaps

- date: 2026-10-08
- review target: YM R9B.3 Windows rehearsal return
- CodeDiff/review baseline applied: `hardening/v2.6@ee30144bc0314bde3b64983a3f44a9209a5a337e`
- baseline evidence: Harness Full Validation #123 = SUCCESS
- baseline status: `HARDENED SHADOW CANDIDATE` (not ENFORCED authority)

## Finding 1 — N4 stale/freshness negative did not reach freshness logic

**Class:** `EVIDENCE_GAP / NEGATIVE_TEST_FALSE_COVERAGE`  
**Severity:** high

The returned N4 case named `n4a_captured_2019` changes `captured_at_utc` to 2019, but does not
re-bind the changed capture SHA into the harness/completion artifacts.

The evaluator therefore denies at:

`HARNESS_CAPTURE_SHA_MISMATCH`

before it reaches the time-order/freshness checks.

This is useful evidence for capture-tamper binding, but it does **not** prove the stale/replay path
`RUN_TIME_ORDER_INVALID` or `RUN_CONTEXT_NOT_FRESH_AT_EVALUATION`.

### Required correction

Keep the existing N4a result, but relabel it:

`CAPTURE_TAMPER_BINDING_PASS`

Add one real freshness negative using either:

1. the original internally consistent artifact set evaluated after the run context has expired in live-freshness mode, expecting
   `RUN_CONTEXT_NOT_FRESH_AT_EVALUATION`; or
2. a fully self-consistent copied artifact set whose time fields and dependent SHA bindings are all recomputed so evaluation reaches
   `RUN_TIME_ORDER_INVALID`.

Do not mutate the successful original evidence.

## Finding 2 — N5 behavior passes, but returned package omits exit/no-traceback artifacts

**Class:** `EVIDENCE_PACKAGING_GAP`  
**Severity:** medium

The return package includes:
- `broken.denied.json` → `CAPTURE_JSON_INVALID`
- `toplist.denied.json` → `CAPTURE_TOP_LEVEL_NOT_OBJECT`

but does not include dedicated exitcode/stdout/stderr files for N5, despite the closeout claiming exit 2 and no traceback.

Independent re-execution against the exact frozen R9B.3 evaluator reproduced:
- broken JSON: exit 2, stderr 0 bytes, typed DENY
- top-level list: exit 2, stderr 0 bytes, typed DENY

So this is a packaging/evidence-completeness issue, not an evaluator functional defect.

Future negative packets should preserve exitcode/stdout/stderr for every required negative case.

## N6 note

The returned N6 evidence contains:
- server exit code 1
- client exit code 0
- failure record with cleanup attempted

Those process objects had exited when evidence was written, so the required server/client cleanup is supported.
No additional defect is raised for N6 in this review.

## v2.6 authority interpretation

v2.6 hard-floors HIGH/CRITICAL security surfaces to HUMAN. It also remains a SHADOW candidate itself.

Therefore applying v2.6 does not lower the R9B.3 gate. Current maximum remains:

`MEASURED_NOT_AUTHENTICATED / stable_node_id=UNBOUND / NOT_AUTHORIZED / authority_effect=NONE`

and R9C remains blocked until:
- corrected freshness negative evidence is returned; and
- required HUMAN/independent review is satisfied.
