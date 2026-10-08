# R9B.4.3 return — missing anchor sibling and locale-sensitive closure self-test

- date: 2026-10-08
- returned package: `ym_r9b43_package_20261008.zip`
- returned ZIP SHA-256: `e6e3d6d677ab56f8b6cf7d314905d8e51dbb4ae75976ac0bbd1bf911c74ab1d1`
- classification: `EVIDENCE_PACKAGING_GAP / PORTABILITY_TEST_GAP`
- severity: medium
- protocol impact: none
- R9C impact: remains blocked pending HUMAN review

## What independently passed

The final sealed review bundle inside the return was independently rechecked:

- `attachment/R9B43_review_bundle.zip` SHA-256:
  `f040b1f81780ac233335b3d769782fa3a6e868afde611b3350c77ef50461e778`
- inner ZIP CRC: PASS
- `REVIEW_MANIFEST.sha256`: 16/16 exact
- review manifest SHA-256:
  `76b10143d6a1bbba336f88260993b89f9e990ad22543711cfa2cc78ef69c4fe2`
- exact R9B.4.2 `verify_review_safe_set.py` rerun against final extracted bytes:
  `R9B4_OFFLINE_ARTIFACT_SET_BOUND`

Therefore the prior post-verification-mutation defect is closed.

## Finding 1 — documented anchor sibling is absent from the returned package

`docs/GAP_ANALYSIS.md` and `docs/MASKING.md` state that the closure emits/ships
`ANCHOR_TO_PUBLISH.json` as a sibling outside the sealed review ZIP.

The actual returned package has 15 entries and contains no such file.

This does not invalidate the sealed review ZIP hash because the digest can be independently recomputed, but it means
the return package does not itself contain the promised publication payload.

Correction:
- publish the independently recomputed sealed review ZIP digest through a separate immutable GitHub record;
- reference that immutable commit/path in the HUMAN review request;
- do not insert the anchor record back into the sealed review ZIP.

## Finding 2 — closure self-test is locale sensitive on Windows

The returned `pytest_closure.log` shows 4/5 tests passing.

`test_anchor_payload_must_be_outside_review_zip_contract` calls:

`Path.read_text()`

without an explicit encoding. On the Windows locale used by YM this selected cp949 and failed while reading the UTF-8
work packet.

The asserted contract text itself is present and the runtime closure succeeded, so this is a portability-test defect,
not an evidence-integrity failure.

Correction for the next maintenance revision:
- use `read_text(encoding="utf-8")` for UTF-8 package text;
- require closure self-tests to be 5/5 on Windows before claiming test PASS.

## Gate

R9B.4.3 post-seal review-bundle closure may be accepted.

External anchor publication still has to be performed separately.

After anchor publication the remaining blocker is the v2.6 independent/HUMAN review floor.

Security ceiling remains:

`MEASURED_NOT_AUTHENTICATED / UNBOUND / NOT_AUTHORIZED / NONE`.
