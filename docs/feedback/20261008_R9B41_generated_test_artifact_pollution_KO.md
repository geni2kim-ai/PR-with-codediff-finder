# R9B.4.1 package — generated pytest/cache artifacts were sealed into candidate manifest

- date: 2026-10-08
- affected source package: `synapse_boot_auth_r9b41_packaging_authority_cleanup_fix_20261008.zip`
- affected ZIP SHA-256: `1ede044931891fc9fd4def00bab1581d32f27bb5eabc11c7b9998500f495ce63`
- classification: `PACKAGING_GAP / TEST_ARTIFACT_POLLUTION`
- severity: low
- review baseline: `PR-with-codediff-finder v2.6 hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`

## Observed

While preparing R9B.4.2 from the exact R9B.4.1 ZIP, the candidate tree contained 78 generated test/cache files that are not source-of-record:

- `.pytest_cache/**`
- `__pycache__/**`
- `*.pyc`

The R9B.4.1 candidate manifest had sealed these generated files as ordinary package content.

This did not cause the R9B.4.1 verifier-PID runtime defect, but it contradicts the intended clean-package discipline and makes manifests noisier and less reproducible across Python/pytest versions.

## Remediation

R9B.4.2:
- removes all `.pytest_cache`, `__pycache__`, and `*.pyc` before source hashes/manifests are generated;
- regenerates issued-source hashes after cleanup;
- regenerates candidate/root manifests;
- performs clean-extract validation on the final candidate tree;
- keeps generated runtime/test cache artifacts outside the distributable source package.

## Gate

This is a packaging hygiene finding, not an authority finding.

The security ceiling remains:
`MEASURED_NOT_AUTHENTICATED / UNBOUND / NOT_AUTHORIZED / NONE`

R9C remains blocked for the separate Windows rehearsal/review gates.
