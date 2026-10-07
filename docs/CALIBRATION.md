# Reviewer Calibration v2.4

Calibration compares lower reviewer decisions with the highest recorded authority; it does not call that authority absolute ground truth.

Cases are split into at least two sampling strata:
- `random_audit`: unbiased sampling signal;
- `policy_escalation`: harder cases selected by risk/disagreement/novelty.

This avoids treating an escalation-heavy case bank as the natural population and underestimating L1/L2 performance.

Invalid JSON, missing ledgers, anchor mismatches and unavailable HMAC keys for HMAC-protected cases are surfaced in `invalid_or_unanchored_cases`; they are never silently skipped.
