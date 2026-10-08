# R9B.4.2 return — post-verification mutation breaks review-safe binding

- date: 2026-10-08
- returned package: `ym_r9b42_package_20261008.zip`
- returned ZIP SHA-256: `4298587e16c9836da66765aabf7620f22ebc83ebfbd9f387333493e0b0995354`
- review baseline: `PR-with-codediff-finder v2.6 hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`
- Harness Full Validation: #153/#154 SUCCESS
- classification: `EVIDENCE_PACKAGING_GAP / POST_VERIFICATION_MUTATION`
- severity: high
- disposition: `WINDOWS_RUNTIME_PASS_CANDIDATE / REVIEW_BUNDLE_BLOCKED / R9C_BLOCKED`

## What passed

The returned Windows evidence supports:
- exact package manifest 84/84;
- rebuilt R9B.4.2 verifier source SHA matches the issued source;
- verifier PID triple-binding:
  `capture.verifier.pid == completion.verifier_pid == harness.server_pid == 7180`;
- first live evaluator:
  `R9B4_ONE_TIME_EVALUATION_MEASUREMENT_READY`;
- immediate duplicate:
  `R9B4_DENIED / RUN_TOKEN_ALREADY_CONSUMED`;
- replay token name independently recomputes from run_id + NUL + nonce;
- authority ceiling negatives 5/5;
- external pin negatives 5/5;
- production timeout cleanup PASS;
- child-tree cleanup PASS;
- wrong-SID cleanup PASS;
- privacy seal v3 PASS.

## Blocking finding — final review-safe bytes no longer match their binding receipt

The package contains `attachment/review_safe_verify.json` claiming:

`R9B4_OFFLINE_ARTIFACT_SET_BOUND`

However, re-running the exact issued R9B.4.2 `verify_review_safe_set.py` against the **final ZIP bytes** returns:

`R9B4_REVIEW_SAFE_DENIED / BUILD_RECEIPT_EXTERNAL_SHA_MISMATCH`

Direct hash comparison shows two bound files changed after the earlier verification:

- `build.review.json`
  - binding expected: `031db20362727aefe0152f00360fca4d641e8d463dc02e592a043fe388607998`
  - final ZIP actual: `60b77b951ce1cd7e65edc7d6fa5bdff1794e1d951835ec287e182819ba29ff38`
- `cleanup.review.json`
  - binding expected: `18bc5add61e8d986458b813b6ef23130380fde4429e373764751ddb2a7d44398`
  - final ZIP actual: `3794b6b94a769f488c40ddbbb9832581c3add5e7407f7bb9166e1f495fe67580`

The JSON objects are semantically equivalent to their distributable counterparts; the difference is byte-level serialization/line-ending normalization. Because the verifier binds bytes, semantic equivalence does not preserve the evidence contract.

This means a later masking/scrub/package step mutated the review-safe directory **after** the PASS result had been generated.

## Anchor finding

`docs/MASKING.md` states that final anchor material will be written to:

`docs/ANCHOR_MATERIAL.json`

but that file is absent.

More importantly, a final archive cannot contain its own final ZIP SHA without changing that SHA. The external anchor must therefore be a **separate immutable publication/receipt**, not a file inserted back into the reviewed ZIP after sealing.

## Required correction — evidence only, no protocol/source change

R9B.4.3 should be an evidence-packaging closure only:

1. Regenerate the review-safe directory from the original local raw R9B.4.2 artifacts.
2. Run all privacy transformations **before** binding and verification.
3. After `verify_review_safe_set.py` passes, mark the review-safe subtree byte-immutable for packaging; no later scrub/pretty-print/re-serialization.
4. Create the final review ZIP.
5. Extract that ZIP into a fresh directory and re-run:
   - manifest verification;
   - `verify_review_safe_set.py`.
6. Require the post-seal extracted result to be `R9B4_OFFLINE_ARTIFACT_SET_BOUND`.
7. Compute final review ZIP SHA-256.
8. Publish that SHA externally in a separate immutable channel. Do not add the resulting anchor receipt back into the sealed review ZIP.
9. Return the external anchor reference separately.

## Gate

No R9B.4.2 protocol change is required by this finding.

Current maximum state:

`R9B42_WINDOWS_RUNTIME_PASS_CANDIDATE / REVIEW_PACKAGE_BLOCKED`

R9C remains blocked pending post-seal independently replayable review package + HUMAN review.
