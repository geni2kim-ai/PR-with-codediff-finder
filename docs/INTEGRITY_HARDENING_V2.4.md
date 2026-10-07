# Integrity Hardening v2.4

## Trust boundaries

1. Git object database + trusted base ref define changed-file identity.
2. TextDiff evidence is a cache/artifact, not an authority. The harness verifies Git metadata and reproduces its semantic digest with the bundled pinned adapter.
3. Reviewer JSON is untrusted until schema, provenance, output-safety, size, identity, head SHA, and authority checks pass.
4. L1/L2/Adversarial decisions cannot lower deterministic floors.
5. Ledger integrity and reviewer correctness are separate. An HMAC anchor detects unauthorized rewrite of the local event ledger but does not make a reviewer verdict true.

## Rename/copy handling

Both `old_path` and `path` are classified. Moving `auth/login.py` to `lib/login.py` therefore retains the protected-path floor. The same principle applies to governance/workflow files moved away from protected locations.

## Path matching

Patterns without a leading slash match from the repository root or at a complete path-segment boundary. A literal leading `/` is root-anchored. Normalization removes only literal `./` prefixes and rejects parent traversal; it does not strip arbitrary dots.

## Non-text changes

Symlink, submodule, binary, oversized and failed-analysis changes are coverage gaps. They cannot produce trusted L1 evidence. Symlink/submodule/binary changes additionally emit `nontext_sensitive_change`, which requires adversarial review by default.

## Evidence acceptance

Acceptance requires all of:
- base-tip, merge-base and HEAD binding;
- exact Git changed-file metadata match;
- pinned checker/dependency hashes;
- semantic validator pass;
- TextDiff adapter recomputation producing the same `semantic_digest`.

`output_digest` includes execution telemetry; `semantic_digest` intentionally excludes performance telemetry to support deterministic reproduction.

## Reviewer output safety

The harness scans reviewer-controlled strings, including claim, evidence, impact, recommendation, source ref, failure family and escalation reasons. It rejects external schemes, protocol-relative URLs, `www`, common bare domains, markdown/HTML image markup, dangerous markdown schemes, mentions including zero-width obfuscation, and common secret patterns. Worker self-reported safety flags must equal harness-computed flags.

## Ledger model

- Each append is serialized by a lock.
- Each event contains sequence, previous hash and event hash.
- An atomically replaced anchor binds ledger length, tail hash and full ledger SHA-256.
- SHADOW anchors are useful for accidental truncation/corruption detection but are not a cryptographic authority against an attacker that can rewrite both files.
- ENFORCED requires `MAESTRO_LEDGER_HMAC_KEY`; the anchor then includes an HMAC and cannot be validly recreated without the external key.

## ENFORCED boundary

`runtime_attestation.py` verifies an HMAC-authenticated statement emitted by an external launcher. It is evidence that the launcher claims to have applied network/filesystem/env controls; the Python harness does not implement those OS controls itself. Production enforcement still requires real sandbox E2E validation.
