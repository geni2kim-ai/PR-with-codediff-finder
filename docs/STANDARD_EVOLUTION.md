# Standard Evolution v2.4

Adversarial/Human review can identify a `standard_gap`, but no reviewer may directly modify the trusted standard as part of adjudication.

Flow:
1. adjudication identifies wrong layer/failure family/gap;
2. regression fixture is recommended or created;
3. `propose_standard_candidate.py` emits a PROPOSED candidate and logs `STANDARD_CANDIDATE_PROPOSED` when a ledger is supplied;
4. HUMAN + CODEOWNER review is required;
5. policy/standard update is applied in a separate governed change;
6. benchmark/regression corpus is rerun.
