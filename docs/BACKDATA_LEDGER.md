# Backdata / Case Ledger v2.4

A case has two complementary representations:

- `case-record.json`: current materialized snapshot for analytics.
- `case-events.jsonl` + `case-events.anchor.json`: ordered event evidence.

The ledger records sensor acceptance/rejection, completed/failed reviews, escalation, human decisions, outcomes, incidents, RSI evaluations, standard-candidate proposals, blocked/closed cycles.

`validate_case_bundle.py` cross-checks the snapshot and events: reviewer trail digests must have matching events, sensor digest must match, outcome/incident state must be derivable from events, and the anchor must match the ledger. HMAC-protected anchors require the external HMAC key when routed/calibrated.

Central case-bank storage intentionally excludes raw source bodies and full hunks. Sanitized regression fixtures may be created separately under owner-approved rules.
