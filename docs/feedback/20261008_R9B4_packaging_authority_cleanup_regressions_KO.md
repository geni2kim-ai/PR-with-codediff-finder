# R9B.4 candidate review — packaging completeness and authority-ceiling regression

- date: 2026-10-08
- target: `synapse_boot_auth_r9b4_replay_cleanup_binding_hardening_20261008.zip`
- disposition: `DO_NOT_RUN_ON_WINDOWS / REPACKAGE_REQUIRED / R9C_BLOCKED`
- review baseline: `PR-with-codediff-finder v2.6 hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`

## High findings adopted

### H1 — issued package is incomplete

The package omitted core R9B.4 files referenced by its own build/test/handoff:

- `r9b4/src/VerifierServer.cs`
- `r9b4/src/DedicatedMediator.cs`
- `r9b4/src/SyntheticChild.cs`
- `r9b4/evaluate_r9b4.py`
- `r9b4/preflight.py`
- `r9b4/verify_review_safe_set.py`
- `r9b4/provision_registry.py`

Because the manifest was generated over the already-incomplete tree, manifest success did not prove reference completeness.

Remediation:
- repackage from a clean staging tree;
- add a reference-completeness validator;
- run pytest from the packaged tree after ZIP creation/extraction.

### H2 — authority-ceiling validation regressed

R9B.4 evaluator validates `authority_effect` but no longer rejects preclaimed:
- `authentication_result=AUTHENTICATED`
- `authorization_status=AUTHORIZED`
- `runtime_grant_issued=true`
- `g1_token_issued=true`
- `f2_unlocked=true`

The evaluator then emits fixed safe output values, silently laundering unsafe input claims.

Remediation:
- restore explicit authority-ceiling validation across capture/build/registry/preflight/run_context/harness/completion/cleanup;
- output safe ceiling only after those validations pass;
- add negative tests for every authority field.

### H3 — forced cleanup probe can false-pass

The probe records `timeout_path_exercised=true` and `tree_kill_invoked=true` as literals and does not actually invoke the same timeout branch/helper as the production harness.

Remediation:
- factor cleanup into one shared PowerShell helper module/function;
- production harness and forced probe must use the same cleanup implementation;
- force the actual server-timeout branch;
- require `existed_before=true`, tree-kill invocation/result, bounded wait, and `exists_after=false`;
- fail otherwise.

## Medium findings adopted

1. Restore post-run mediator/verifier/source/build/registry SHA checks.
2. Bind cleanup receipt to run_id, session/pipe where applicable, timestamps and process instance evidence.
3. Document replay scope: one-time local ledger only; offline mode is non-consuming by design.
4. Expand review-safe privacy scanning to all output documents and remove low-entropy preimage-checkable value hashes from transformation receipts.
5. Unify status files and explain synthetic local Git lineage vs original issued commit lineage.
6. Include referenced feedback docs or exact immutable GitHub commit/path references.
7. Add package-reference completeness and clean-extract test reproduction as release gates.

## Gate

R9B.4 current ZIP must not be used for Windows rehearsal.

Next acceptable state:

`R9B4_1_PACKAGING_AND_AUTHORITY_REGRESSION_FIXED_STATIC_CANDIDATE`

Even after correction:
`MEASURED_NOT_AUTHENTICATED / UNBOUND / NOT_AUTHORIZED / NONE`
and R9C remains blocked pending Windows rehearsal plus independent/HUMAN review.
