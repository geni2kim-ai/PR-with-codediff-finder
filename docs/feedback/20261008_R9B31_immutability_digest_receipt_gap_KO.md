# R9B.3.1 v2.6 closure — source/original immutability proof packaging gap

- date: 2026-10-08
- target: YM R9B.3.1 evidence-closure return
- review baseline: `hardening/v2.6@ee30144bc0314bde3b64983a3f44a9209a5a337e`
- baseline validation: Harness Full Validation #123 = SUCCESS
- classification: `EVIDENCE_PACKAGING_GAP`
- severity: low

## What passed

The returned closure package independently supports:

- manifest: 18/18 exact match;
- freshness negative: exit 2, stderr empty, exact typed deny
  `RUN_CONTEXT_NOT_FRESH_AT_EVALUATION`;
- malformed JSON: exit 2, stderr empty, `CAPTURE_JSON_INVALID`;
- top-level list: exit 2, stderr empty, `CAPTURE_TOP_LEVEL_NOT_OBJECT`;
- closure summary: PASS;
- privacy seal v3 over the distributable closure: PASS / 0 matches;
- no raw successful capture, raw registry, or real SID distributed.

Therefore the previously open freshness-negative and N5 packaging gaps are closed.

## Remaining evidence-packaging gap

`docs/VALIDATION.md` and `docs/CHANGELOG.md` report that the original successful capture/registry and other
run artifacts were re-hashed and remained unmodified.

The distributable closure, intentionally, does not contain those raw artifacts. However it also does not carry a
safe before/after digest receipt for those originals.

As a result, a reviewer of the returned closure can verify the negative outputs but cannot independently verify the
specific claim:

`original successful artifacts were unchanged before vs after closure execution`

without access to the original local files.

This does **not** invalidate the closure result because the work unit intentionally prohibited redistribution of raw
SID-bearing evidence. It is an evidence-completeness issue only.

## Recommended future pattern

For privacy-sensitive evidence-only closures, return a digest-only mutation receipt such as:

- artifact logical name;
- pre-run SHA-256;
- post-run SHA-256;
- equality boolean;
- no filesystem path;
- no SID/content;
- receipt schema/version;
- authority_effect = NONE.

This gives independent immutability evidence without redistributing the protected raw files.

## Gate

R9B.3.1 technical evidence closure may be accepted.

This finding does not reopen R9B.3 source remediation.

The v2.6 HUMAN floor remains separate and unsatisfied, so R9C remains blocked pending the required independent/human review.
