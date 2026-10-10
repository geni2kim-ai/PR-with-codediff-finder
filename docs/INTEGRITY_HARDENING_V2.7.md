# Integrity Hardening v2.7

## Threat model extension

v2.7 adds a specific failure model that v2.6 did not fully close: **the process can stop at any mutation boundary and later resume with only durable files remaining**.

The design therefore treats recovery files, locks, immutable case-bank entries, trusted references and effective policy snapshots as integrity boundaries rather than convenience state.

## Closed boundaries

### Ledger append crash window

Before mutating the JSONL ledger, the harness writes an append transaction containing the exact prior ledger byte digest, prior event hash, next event, a logical event-instance identifier when supplied, and an optional HMAC. Pending recovery verifies any existing pre-append or post-append anchor snapshot (seq/hash/ledger SHA, case ID, key ID and configured HMAC) **before** repairing a torn tail or replacing an anchor. Both direct recovery and `append_event()` retry perform this preflight **before creating or promoting the sticky auth witness**; invalid anchors therefore cannot leave behind a newly poisoned witness. A missing anchor with prior events (pre_seq > 0) fails closed; only the first append can legitimately have no pre-anchor. Invalid pending event schema is rejected before replay. The digest is always an integrity check; the journal is authenticated only when HMAC authority is configured. If the ledger ends with an exact byte-prefix of the pending event, recovery verifies the pre-ledger SHA-256, truncates only that proven prefix, fsyncs, and retries the append. A malformed tail that is not the pending event prefix raises a typed `LedgerTornWriteError` and is not guessed or repaired.

### Dead lock recovery

The ledger lock records owner PID, a process-instance identifier where the OS exposes one, and hashed machine/hostname/node identity components. Reclamation is limited to a stale lock attributable to the same host and is serialized through a separate reclaim guard, preventing a second reclaimer from deleting a freshly acquired lock.

### Ledger HMAC downgrade boundary

When an HMAC-backed ledger is created, v2.7 writes a sticky local `case-events.auth.json` witness outside the anchor. Validation also treats a non-null anchor/transaction `key_id` as an HMAC requirement. Deployments that need the requirement to survive deletion or rewriting of every local ledger-side trust file must provide an external expectation through `MAESTRO_LEDGER_EXPECT_KEY_ID` or the validation CLI `--expected-key-id`, together with the HMAC key. This external expectation is the fail-closed authority boundary; a fully mutable local bundle cannot cryptographically prove that an attacker deleted evidence of earlier HMAC use.

Unsigned journals therefore provide digest/hash-chain integrity and deterministic crash recovery, not authentication. “Authenticated recovery journal” applies only to the HMAC-configured path. An existing unsigned ledger cannot switch to signed mode implicitly via `append_event()`: such a request is rejected **before** writing a sticky auth witness, so a failed signing attempt cannot lock out subsequent legitimate unsigned writes. Pending journal recovery with a missing witness authenticates the signed transaction **before** establishing a replacement witness; malformed/unsigned journals cannot promote the HMAC requirement by self-declaration. Signed-mode migration of existing unsigned history requires an explicit operator-approved procedure. A preexisting anchor or pending journal is verified **before** any sticky-witness update: forged HMAC markers, invalid signatures, and mismatched key IDs cannot poison the witness. Newly submitted event data is checked against the v2.4 event schema and JSON serialization requirements before writing any ledger-side files.

### Duplicate append semantics

The recovery journal may carry `event_instance_id`. During a pending-journal recovery, repeating the same logical request with the same identifier **and matching case/type/payload/explicit timestamp** returns the recovered event idempotently. Reusing that identifier with conflicting event data raises typed `EVENT_INSTANCE_CONFLICT` after safely completing the pending recovery, rather than silently dropping the caller's request. A distinct identifier (or a new request with no identifier) creates a separate event, even when type/payload match. **Scope:** the identifier currently exists only in the pending journal; after successful transaction cleanup, the v2.4 event schema does not retain it, so this is not a general post-commit exactly-once/replay guarantee. A durable receipt/index or versioned schema extension with migration is required for that stronger contract.

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
- emits a separate source-package receipt binding exact HEAD, ZIP SHA-256, manifest SHA-256 and manifest entry count; when created in GitHub Actions it also records validation run ID, run attempt and workflow ref for traceability.
- rejects tracked pytest/Python cache artifacts before manifest generation so generated test state is not sealed as source-of-record.

The package receipt is an integrity/binding/traceability record with `authority_effect=NONE`. Its self-digest binds the recorded run metadata, but GitHub Actions/artifact metadata (or another external witness) is still required to prove that the referenced run actually existed; the receipt is not an external signature or promotion authority.

### JSON and filesystem redirect boundaries

The ledger writer now requires strict finite JSON values before creating any ledger-side file. Python's default JSON encoder accepts `NaN` and `Infinity`, which are not interoperable strict JSON and could otherwise become permanently anchored in an audit ledger; journal and ledger readers reject these values (including exponents that overflow to non-finite Python floats). A malformed non-object pending transaction is a typed fail-closed recovery result.

Before append, recovery, anchor write and anchor validation, existing ledger/anchor/journal/witness/lock paths and their ancestor components are checked for symlinks or Windows junction redirects. Dangling ledger symlinks are rejected before any file creation; a redirected parent directory cannot silently turn local writes into external writes. Checks repeat inside the ledger lock on mutation paths. These are conservative filesystem checks, **not** a claim of race-free containment against hostile concurrent directory replacement: full sandbox enforcement and descriptor-relative protections remain external promotion gates.

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

### Standalone ledger validation invariants

An individual ledger must contain one case ID even when the caller does not supply `--case-id`. The common validator infers the first valid case ID and rejects later cross-case events, including when unsigned event hashes and the local anchor have been recomputed consistently. Existing malformed/mismatched auth-witness files cause anchor-validation errors instead of being treated as absent; legitimately absent witnesses retain their existing compatibility behavior. Non-object JSON event values and non-object anchors produce validation errors rather than unhandled attribute-access exceptions.
