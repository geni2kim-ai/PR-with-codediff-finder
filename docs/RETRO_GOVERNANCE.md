# Retro / Davinchi Governance

Retro can propose changes, not silently rewrite authority.

Every proposal records: stable rule/family ID, motivating cases, affected scope, good/bad examples, deterministic detection when feasible, severity, false-positive risk, regression fixtures, owner, creation/review/expiry dates, and supersession links.

Required controls:
- review-policy/standards/check/CODEOWNERS/workflow changes require human/CODEOWNER approval;
- proposal author/reviewer cannot self-approve;
- prefer deterministic enforcement when possible;
- deduplicate rules and retire noisy/redundant ones;
- lowering security or human-review requirements is always a governance change;
- accepted changes rerun golden/historical benchmark before rollout.
