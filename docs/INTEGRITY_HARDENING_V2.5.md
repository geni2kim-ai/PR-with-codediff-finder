# Integrity Hardening v2.5

## Temporal binding
A review is about a tuple, not only a HEAD SHA:

`repository + trusted base ref tip + merge-base + candidate HEAD`

At cycle close the harness re-resolves the trusted base ref and recomputes merge-base. A moved target branch invalidates the old cycle as `STALE`.

## Runtime attestation
ENFORCED accepts an external attestation only when:
- HMAC is valid;
- workspace matches;
- case id matches;
- base SHA matches the reviewed merge-base;
- HEAD SHA matches;
- required runtime controls are true;
- `issued_at` is within configured age/future-skew bounds;
- nonce syntax is valid and its one-time replay token can be atomically claimed in the external replay cache.

Accepted attestation digest and replay token are appended to the ledger as `RUNTIME_ATTESTED`, and the attestation digest is propagated to reviewer tasks. ENFORCED requires `MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR` outside the repository. The replay cache is a launcher/host trust boundary: if untrusted code can delete its claim files, replay protection is not authoritative.

## Reviewer executable provenance
`worker_command_digest` canonicalizes command argv. Existing executable/script arguments are represented by filename + byte SHA-256; non-file arguments are literal. This is not proof of remote model identity, but it makes local worker implementation drift visible to calibration.

## Environment minimization
The reviewer environment is rebuilt from an allowlist. Secret-like variable names are rejected by configuration validation and suppressed defensively by the worker launcher.

## Remaining trust boundary
v2.5 still does not create an OS sandbox. ENFORCED requires an external launcher and protected keys. A valid attestation proves only that the trusted issuer made the statement; deployment must separately validate that the issuer really applies the claimed isolation.
