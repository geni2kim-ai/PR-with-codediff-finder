# Integrity Hardening v2.7

## Threat model extension

v2.7 adds a specific failure model that v2.6 did not fully close: **the process can stop at any mutation boundary and later resume with only durable files remaining**.

The design therefore treats recovery files, locks, immutable case-bank entries, trusted references and effective policy snapshots as integrity boundaries rather than convenience state.

## Closed boundaries

### Ledger append crash window

Before mutating the JSONL ledger, the harness writes an append transaction containing the exact prior ledger byte digest, prior event hash, next event and optional HMAC. Recovery accepts only the exact interrupted transition.

### Dead lock recovery

The ledger lock records its owner PID. A subsequent process may reclaim the lock immediately when that process no longer exists, instead of waiting for an arbitrary age threshold that exceeds the caller timeout.

### HUMAN transaction recovery

The HUMAN transaction is bound by:
- canonical transaction digest;
- HUMAN authority-key HMAC;
- source cycle digest;
- evidence digest;
- reviewed HEAD;
- attestation digest;
- deterministic transaction ID.

Freshness is checked at decision acceptance. Historical verification of an already accepted ledger-bound HUMAN decision checks cryptographic proof and binding without incorrectly expiring the decision later.

### Immutable case-bank reuse

An existing immutable case directory is recoverable only when the current case record equals the stored immutable record and its adversarial packet binding/evidence digest agrees.

### Trusted input and policy freeze

Standards, spec and test result files are copied into the cycle output before reviewer execution. Policy files are copied into `effective-policy/`. All later task provenance, routing, sensor recomputation and evidence validation consume those frozen copies.

### Source-package delivery boundary

A Git-blob manifest PASS is not treated as proof that a distributed ZIP is complete. PR/manual packaging now:
- creates the ZIP directly from exact Git blob bytes of the validated HEAD, avoiding archive-time text-byte transformation;
- extracts the ZIP into a clean directory;
- verifies the extracted tree against `MANIFEST.sha256` without relying on `.git`;
- rejects extra, missing, changed or path-ambiguous entries;
- reruns canonical full validation from the extracted tree;
- emits a separate source-package receipt binding exact HEAD, ZIP SHA-256, manifest SHA-256 and manifest entry count.
- rejects tracked pytest/Python cache artifacts before manifest generation so generated test state is not sealed as source-of-record.

The package receipt is an integrity/binding record with `authority_effect=NONE`; it is not an external signature or promotion authority.

## Review invariant

The repository-level default is **Latest-HEAD review**. A previous PASS cannot authorize a newer HEAD.

## Remaining external gates

v2.7 does not claim completion of:
- OS-enforced network/filesystem sandbox E2E;
- protected external attestation issuer/key infrastructure;
- real independent L1/L2/Adversarial model-session issuance;
- GitHub required-check/ruleset production E2E;
- production post-merge incident connector/calibration;
- Windows-specific process/path/GUI packaging E2E.
