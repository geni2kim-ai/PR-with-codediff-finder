# R9B.4.4 non-authoritative review — rebinding, evidence-byte provenance, and replay precision gaps

- date: 2026-10-08
- target: `synapse_boot_auth_r9b44_human_review_completeness_cleanup_hardening_20261008.zip`
- classification: `REVIEW_EVIDENCE_PRECISION_GAP`
- severity: low-to-medium
- authority effect: NONE
- R9C: BLOCKED

## R1 — complete rebinding map misses preflight SID masking

`make_review_safe_bundle.py` directly assigns the masked SID to `preflight["allowed_user_sid"]`.
That change is not produced by the recursive transform helper and therefore is absent from the transformation receipt and
R9B.4.4 `REBINDING_MAP.json`.

Correction:
- generate the privacy/change inventory automatically from pre-transform vs final review documents;
- include direct privacy transforms **and** all derived hash rebindings;
- specifically require `/preflight/allowed_user_sid`.

## R2 — `copied_byte_for_byte=true` overstates runtime-byte provenance

The HUMAN supplement files are copied byte-for-byte from the packaged YM return ZIP, but several packaged text files are
LF-normalized relative to the byte form hashed by the Windows harness.

Confirmed examples:

1. timeout cleanup
   - packaged LF SHA: `7d1b349da91970186c6f174f3e01ca5aa360f4917b7ac3c1766e15782d50987e`
   - CRLF reconstruction: `0c5d9939163d287b7f9a29f2aef25e14f46d5528adf46528d8c87307e26517f1`
   - harness-recorded SHA: `0c5d9939163d287b7f9a29f2aef25e14f46d5528adf46528d8c87307e26517f1`

2. wrong-SID cleanup
   - packaged LF SHA: `22a182f732eadfdc12c4ca583151043663447eddbe663b18aa7d9fbace4b4696`
   - CRLF reconstruction / harness SHA: `c8015b52c110bafb09affe3c03b5ff06e251e69a53d32dac7b0714b9a30c8868`

3. wrong-SID server stderr
   - packaged LF SHA: `c37449ab5b00cb36b7a84939dc345565aa4d1126577f9c0185a8f4dd4f0a8266`
   - CRLF reconstruction / harness SHA: `77c1e19c79f9ed77612d61e603b702f41fae3fe47071f4ca9cef2ce593ad479e`

Correction:
- replace `copied_byte_for_byte` with explicit provenance:
  - copied byte-for-byte from packaged YM ZIP;
  - runtime byte identity not claimed when harness digest differs;
  - record packaged SHA, harness-recorded SHA, normalization type, and reconstructed digest when provable;
- externally publish the source YM ZIP SHA:
  `4298587e16c9836da66765aabf7620f22ebc83ebfbd9f387333493e0b0995354`.

## R3 — duplicate replay denial lacks self-describing execution binding

The historical `R9B4_live_result_dup.json` contains only the denial code and authority-ceiling fields. It does not carry:
- evaluation timestamp;
- evaluator hash;
- replay implementation hash;
- run_id / nonce;
- input evidence set hash.

Therefore the duplicate file alone cannot prove that the exact same input set was submitted to the exact evaluator.

Correction for R9B.4.5:
- every live evaluator result, including replay denial, must include:
  - `evaluation_time_utc`;
  - `evaluator_cli_sha256`;
  - `evaluator_core_sha256`;
  - `replay_impl_sha256`;
  - `run_id`;
  - `measurement_nonce`;
  - deterministic `input_set_sha256`;
  - per-input evidence digests.
- require a fresh Windows live evaluation and immediate same-ledger duplicate so these fields are produced at runtime.

## Scope

R9B.4.5 should remain evidence/review precision hardening. No stable-node authentication, runtime grant, G1, F2, or R9C
activation is authorized.
