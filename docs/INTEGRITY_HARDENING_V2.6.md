# Integrity Hardening v2.6

v2.6 focuses on authority and evidence integrity discovered during direct adversarial reproduction of the v2.5 package.

## Trust boundaries
- Git paths are exact data for Git lookups; normalized paths are policy-only data.
- Review output is untrusted until harness-computed safety checks pass.
- `review-cycle.json` is a projection; ledger `CYCLE_CLOSED` is the authoritative binding used by check rendering.
- HUMAN decisions require an external HMAC-backed attestation and the same reviewed HEAD.
- Existing HMAC ledger history cannot silently downgrade to an unsigned anchor **when the validator retains HMAC authority/expectation or another trusted witness of signed mode**. A pre-existing ledger file also cannot restart from seq=1 merely because it was truncated to zero bytes and its anchor was deleted.
- Deletion or rewriting of every local ledger-side trust artifact is not distinguishable from first creation by local files alone; ENFORCED deployments therefore still require protected external key/expectation or a durable witness/storage boundary.
- ENFORCED runtime/fresh-session claims must originate in signed external attestation.

## Authority invariants
A human floor can be caused by protected paths, governance, risk matrix, security/data/availability signals, destructive migration, public contract break, irreversible external side effects, ruleset/CODEOWNERS changes, or unresolved adversarial findings. Configuration may add escalation; it may not reduce these floors.

## Sensor invariants
- merge-base → HEAD remains canonical;
- old/new rename paths both participate in policy classification;
- Git filename spelling is preserved for object access;
- MODIFIED text evidence requires both blob identities;
- non-text/coverage gaps cannot claim trusted gate evidence;
- deterministic non-minimal algorithms are distinct from heuristic fallbacks;
- tool pins must exist and match.

## Runtime invariants
- reviewer input is prepared before process launch;
- output/stderr are bounded while running;
- timeout kills the process tree;
- command provenance binds argv, cwd, executable/script and resolvable `-m` module source;
- secret-like environment names are not forwarded.
