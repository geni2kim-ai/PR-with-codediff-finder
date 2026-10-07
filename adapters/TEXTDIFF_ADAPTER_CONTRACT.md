# TextDiffChecker Evidence Adapter Contract v2.4

The adapter is a deterministic sensor, not the review authority.

Required binding:
- repository/work unit;
- trusted base-tip SHA;
- merge-base SHA;
- HEAD SHA;
- per-file new and old paths for rename/copy;
- base/head blob SHA and mode;
- tool/config/dependency hashes;
- algorithm trace and quality class;
- invariants and trust reasons;
- semantic and execution digests.

The review harness must not trust a supplied evidence JSON solely because its digest validates. v2.4 rechecks Git metadata and reruns the bundled adapter to reproduce the semantic digest.

Non-text or unanalysed changes are explicit coverage gaps. Legacy encodings are LOW confidence unless a future detector proves the charset.
