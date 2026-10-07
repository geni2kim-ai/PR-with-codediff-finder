# GitHub / Local PR Review Harness v2.5

v2.5 is the first release developed **under v2.4 SHADOW self-review (dogfooding)**. It keeps the v2.4 evidence/gate hardening and adds temporal trust, reviewer execution provenance, and validation-runner hardening.

> Package version: **2.5**
> Wire/schema compatibility: existing JSON objects remain `schema_version: "2.4"`; v2.5 adds backward-compatible optional provenance fields and one new ledger event type.

```text
stable baseline v2.4
      ↓ SHADOW review of candidate changes
candidate v2.5
      ↓
TextDiff evidence → L1 → L2 → Adversarial → Human
      ↓
case/ledger + dogfood findings
      ↓
Leonardo/Davinchi improvement loop
```

## What v2.5 adds

- **base-ref freshness**: HEAD and the trusted base ref/merge-base are re-resolved at review close; either moving makes the cycle `STALE`;
- **runtime-attestation freshness/context binding**: ENFORCED attestation is bound to workspace + case id + base SHA + head SHA and rejected when stale/future-skewed;
- **truthful sandbox signaling**: workers receive `MAESTRO_REVIEW_SANDBOX_VERIFIED=1` only when externally attested controls were verified; the old unconditional sandbox claim is removed;
- **runtime attestation provenance**: an accepted attestation is recorded as `RUNTIME_ATTESTED` in the case ledger and its digest is propagated into reviewer tasks;
- **attestation replay defense**: ENFORCED consumes each attestation nonce exactly once through a launcher-owned replay cache outside the repository;
- **reviewer worker fingerprint**: configured worker argv plus executable/script bytes are bound to `worker_command_digest` and retained in case backdata/calibration;
- **environment allowlist defense**: secret-like environment variable names are rejected at runtime config and defensively not forwarded;
- **validation runner hardening**: child test output uses files instead of inherited pipes and multiprocessing-sensitive tests are isolated in explicit OS-process groups; test enumeration is disposable, descendant process groups are cleaned after each run, and a coverage guard fails if registered test modules contain tests missing from the validation groups.

## Stable v2.4 protections retained

- merge-base → HEAD diff;
- rename/copy old + new path classification;
- protected-path floors and deterministic escalation;
- evidence revalidation against Git plus deterministic sensor recomputation;
- binary/symlink/submodule coverage escalation;
- reviewer output size/time/safety enforcement;
- anchored/HMAC ledger;
- L1/L2 independent context and Adversarial-only lower-layer visibility;
- Case Bank / RSI / calibration / standard-candidate governance.

## SHADOW workflow

1. Freeze the stable reviewer version used as the judge.
2. Commit the candidate code change.
3. Generate evidence with the **stable** adapter, not the candidate adapter.
4. Run the stable review cycle in `SHADOW`.
5. Preserve its authority result even when the candidate's own tests pass.
6. Fix candidate issues, rerun, and store the dogfood summary in backdata.
7. Never allow the candidate version to be its own final approval authority.

See `docs/DOGFOOD_WORKFLOW.md` and `DOGFOOD_V2.4_TO_V2.5_KO.md`.

## Recommended operating pattern: use v2.5 as the stable SHADOW baseline

For the next coding change, keep **v2.5 frozen as the stable SHADOW reviewer** and let it review the candidate version. The candidate must never be its own final approval authority.

Recommended loop:

```text
stable v2.5 SHADOW baseline
        ↓
actual development / code change
        ↓
TextDiff evidence
        ↓
L1 self-review
        ↓
L2 independent review when required
        ↓
Adversarial review for disagreement, novel failures, high risk, or low confidence
        ↓
Human authority when the policy floor requires it
        ↓
fix / rerun / close
        ↓
Case Bank + ledger + outcome + post-merge feedback
        ↓
Leonardo reviewer calibration / backdata
        ↓
regression fixture / standard candidate / next improvement
```

Operational tips:

- Keep the stable reviewer version immutable during one candidate cycle. Upgrade the baseline only after the candidate has been independently reviewed and accepted.
- Run the stable adapter/reviewer on each meaningful change bundle, not only once at the end. This preserves *when* a defect entered and *which* review level first detected it.
- Preserve L1, L2, Adversarial, and Human decisions as an append-only review trail. Do not overwrite an earlier verdict when a higher layer disagrees.
- Treat `L1 != L2`, deterministic-sensor disagreement, protected/governance paths, novel failure families, blocker candidates, or low-confidence results as escalation candidates.
- Use random audits on otherwise easy L1 cases so calibration is not based only on difficult escalated cases.
- Record author action (`fixed`, `rejected`, `accepted risk`), merge outcome, and post-merge incidents. These later outcomes are stronger calibration labels than reviewer self-reports.
- Promote repeated confirmed misses into regression fixtures and standard candidates. A reviewer or RSI component may propose a standard change, but must not approve its own rule change.
- Keep raw source/hunk content out of centralized backdata where possible; retain hashes, bounded evidence, failure-family labels, provenance, and outcome metadata instead.
- Do not switch to ENFORCED merely because SHADOW accuracy looks good. Require the external sandbox/attestation, real worker adapters, GitHub required-check E2E, and sufficient calibration evidence first.

This means normal local coding activity becomes useful review data automatically: **the more real code is produced and reviewed, the larger the Leonardo calibration/backdata corpus becomes**. Over time, reviewer accuracy should be measured per layer and per failure family rather than as one overall score.

## Evidence generation

```bash
python tools/textdiff_adapter.py \
  --repo /repo \
  --repository owner/repo \
  --base origin/main \
  --head HEAD \
  --work-unit WU-001 \
  --output /review/CASE-001-evidence.json
```

## Shadow review cycle

```bash
python tools/run_review_cycle.py \
  --repo /repo \
  --evidence /review/CASE-001-evidence.json \
  --expected-base origin/main \
  --case-id CASE-001 \
  --output-dir /review/cases/CASE-001 \
  --l1-cmd-json '["python","l1_worker.py"]' \
  --l2-cmd-json '["python","l2_worker.py"]'
```

The cycle is invalidated if HEAD **or the trusted base ref/merge-base** changes before close.

## ENFORCED runtime attestation

ENFORCED still requires a real external launcher that actually applies OS/network/filesystem controls. `runtime_attestation.py` only creates/verifies the authenticated statement format; it does **not** create the sandbox.

The attestation must bind:

- workspace;
- case id;
- merge-base SHA;
- reviewed HEAD SHA;
- required sandbox assertions;
- recent `issued_at`;
- external HMAC key.

Example format helper after the launcher has applied controls:

```bash
python tools/runtime_attestation.py create \
  --workspace /repo \
  --case-id CASE-001 \
  --base-sha <merge-base-sha> \
  --head-sha <head-sha> \
  --output /secure/runtime-attestation.json
```

## Validation

Canonical command:

```bash
python tools/run_validation.py --full
```

v2.5 intentionally isolates multiprocessing-sensitive regression groups in separate OS processes. See `VALIDATION_COMMANDS.md` and `VALIDATION_REPORT_KO.md` for the exact validation performed for this package.

## Deployment status

**HARDENED SHADOW / DOGFOOD CANDIDATE.**

Do not switch to production merge-blocking ENFORCED mode until the remaining external dependencies are proven end to end:

1. actual OS network deny and workspace-only filesystem sandbox;
2. protected external attestation issuer/key handling;
3. actual L1/L2/Adversarial worker adapters and fresh-session proof;
4. GitHub Check Run + ruleset/branch-protection E2E;
5. production post-merge incident connector and sufficient calibration data.
