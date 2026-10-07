# Backdata Ledger v2.3

Each review case has two representations:

1. `case-record.json` — current materialized snapshot for analysis and RSI.
2. `case-events.jsonl` — append-only hash-chained event history.

The ledger records case opening, sensor acceptance, review completion, escalation, human decision, outcome, incident, RSI evaluation, standard candidate and cycle close events. Every event binds `seq`, `prev_hash` and `event_hash`. `case_ledger.py validate` detects edits, deletion/reordering and cross-case mixing.

The snapshot may be updated when merge/outcome/incident information arrives; the ledger is the audit history proving how it changed.

## Why keep lower-layer decisions
L1 findings are never overwritten by L2, and L2 is never overwritten by Adversarial/Human. A later incident may show that a lower layer was correct and a higher layer was wrong. This disagreement history is training/evaluation data, not noise.

## Privacy
Central backdata stores hashes, paths, classifications, findings and bounded references. Raw source bodies and diff hunks remain in the repository unless a separately approved sanitized regression fixture is created.
