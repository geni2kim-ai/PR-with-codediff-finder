# GitHub / Local PR Review Harness v2.6

v2.6 is the hardening release produced from the external v2.5 adversarial review. It keeps the v2.5 stable SHADOW operating model and closes authority, ledger, sensor, output-safety, and worker-runtime bypasses found by direct reproduction.

> Package version: **2.6**  
> Wire compatibility: reviewer/task/evidence/event JSON objects intentionally retain the established `schema_version: "2.4"` wire contracts unless a specific v2.6 runtime/policy document says otherwise.

```text
stable v2.5 SHADOW baseline
        ↓
candidate v2.6
        ↓
TextDiff evidence
        ↓
L1 → L2 → Adversarial → Human
        ↓
anchored Case Bank + outcome/incident feedback
        ↓
Leonardo/Davinchi calibration / regression / standards loop
```

## v2.6 hardening highlights

- **Canonical ledger anchor**: `case-events.anchor.json`; post-cycle tools use the same anchor and validate it before mutation.
- **No HMAC downgrade**: an HMAC-backed ledger cannot be appended without the key, and deleting the anchor cannot silently restart history.
- **Real HUMAN floor in the cycle**: human-floor paths, high/critical security surface, hard reversibility and other deterministic floors cannot stop at Adversarial.
- **Harness self-protection**: when this repository reviews itself, `tools/**`, `tests/**`, `vendor/**`, requirements and integrity files are governance/HUMAN protected without imposing that floor on unrelated application repositories.
- **Case-insensitive policy matching** with exact Git-path preservation.
- **HUMAN terminal transition**: signed external human-decision attestation + current HEAD check + anchored ledger validation produces `HUMAN_CONFIRMED` or `HUMAN_REJECTED`.
- **Cycle/ledger binding**: GitHub check rendering rejects a recomputed-but-forged `review-cycle.json` unless it matches the latest `CYCLE_CLOSED` ledger event.
- **Backslash-path false-exact fix**: Git paths remain exact for Git object lookup while policy matching normalizes separately.
- **Quality classification**: deterministic non-minimal diff paths use `DETERMINISTIC`; heuristic fallbacks remain `HEURISTIC`.
- **Stronger output safety**: normal code identifiers such as `java.net.URL` are not mistaken for domains, while URL schemes/reference-host fields/zero-width mentions/common secrets/tokens/JWT/Bearer/DB URLs are checked by the harness.
- **Unicode-safe JSONL and weakening scans**: LF is the physical boundary; U+2028/U+2029/U+0085 and form-feed no longer alter parsing semantics.
- **Worker bounds**: stdin is file-backed before launch, stdout/stderr are capped while running, and timeout kills the reviewer process tree.
- **Deterministic policy signals are live**: destructive migration, public-contract break, CODEOWNERS/ruleset changes, payment/billing changes and deterministic-reviewer conflict are generated and routed.
- **Reproducible random audits**: selection is derived from external audit seed + case/head/level; ENFORCED forbids `--disable-random-audit`.
- **Worker provenance** includes cwd and resolvable `python -m` module source bytes.
- **Validation auto-discovery** includes new `tests/test_*.py` modules so a new test file cannot silently miss the canonical run.

## Authority model

```text
SENSOR
  ↓
L1 — high-volume first review
  ↓ when policy/signal requires
L2 — independent cross-check
  ↓ on disagreement, novelty, protected risk, deterministic conflict
ADVERSARIAL — independent adjudication
  ↓ when HUMAN floor applies
HUMAN_REQUIRED
  ↓ external signed human decision + same reviewed HEAD
HUMAN_CONFIRMED / HUMAN_REJECTED
```

The harness may raise authority but may not lower a deterministic HUMAN floor. A mock/model PASS is not authorization to bypass that floor.

## Recommended operating pattern

Keep the prior stable reviewer frozen while reviewing a candidate release. After v2.6 is independently accepted, it can become the next stable SHADOW baseline.

```text
actual code change
   ↓
TextDiff evidence
   ↓
L1
   ↓
L2 when required
   ↓
Adversarial when required
   ↓
Human authority when required
   ↓
fix / rerun / outcome
   ↓
Case Bank + ledger
   ↓
Leonardo reviewer calibration / backdata
   ↓
regression fixture / candidate standard / next release
```

Operational rules:

- freeze the reviewing baseline for a candidate cycle;
- bind every case to base SHA, head SHA, sensor digest, reviewer provenance and policy/standards digest;
- preserve disagreements instead of overwriting lower-layer verdicts;
- separate random-audit strata from risk escalation in calibration;
- treat author fixes, merge outcomes and post-merge incidents as stronger labels than reviewer self-reports;
- centralize hashes/structured evidence rather than raw proprietary source where possible;
- a reviewer/RSI component may propose its own improvement but may not approve its own rule or promotion;
- do not move to ENFORCED merely because SHADOW accuracy is high.

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

## SHADOW review cycle

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

The cycle becomes stale if HEAD or the trusted base ref/merge-base changes before close.

## HUMAN decision

`record_human_decision.py` no longer accepts an unauthenticated self-declaration. The current HEAD, anchored cycle and an external HMAC-backed human-decision attestation must agree. The one-time nonce cache is external authority state: configure one shared cache outside the mutable case bundle and do not vary it per invocation.

```bash
export MAESTRO_HUMAN_DECISION_REPLAY_DIR=/secure/maestro/human-replay-cache

python tools/human_decision_attestation.py create \
  --case-id CASE-001 \
  --actor-id owner-1 \
  --verdict CONFIRMED \
  --head-sha <reviewed-head> \
  --cycle-digest <review-cycle.cycle_digest> \
  --evidence-digest <case-record.sensor.evidence_digest> \
  --output /secure/human-decision.json

python tools/record_human_decision.py \
  --case /review/cases/CASE-001/case-record.json \
  --cycle /review/cases/CASE-001/review-cycle.json \
  --ledger /review/cases/CASE-001/case-events.jsonl \
  --repo /repo \
  --attestation /secure/human-decision.json \
  --review-id H-001 \
  --node-id owner-1 \
  --verdict CONFIRMED
```

## ENFORCED runtime attestation

ENFORCED still requires a trusted external launcher that actually applies network/filesystem/secret isolation. The attestation helper authenticates the statement; it does **not** create the OS sandbox.

The v2.6 attestation binds workspace, case/base/head, sandbox assertions, freshness nonce/timestamp, plus external claims that the L2 and Adversarial sessions are fresh. These fresh-session claims are **fail-closed by default**: the launcher must explicitly assert them.

```bash
python tools/runtime_attestation.py create \
  --workspace /repo \
  --case-id CASE-001 \
  --base-sha <merge-base-sha> \
  --head-sha <head-sha> \
  --l2-fresh-session \
  --adversarial-fresh-session \
  --output /secure/runtime-attestation.json
```

## Validation

Canonical command:

```bash
python tools/run_validation.py --full
```

Validated candidate results:

- harness: **100 PASS** across 51 isolated groups;
- vendored TextDiffChecker: **144 PASS, 1 GUI skip** in this Linux environment;
- DIFF-FALSE-EXACT fixture: PASS;
- schema/semantic examples, review cycle, ledger anchor, case bundle, packet, adjudication and standard candidate: PASS;
- latest GitHub Actions canonical full validation: **SUCCESS** (Harness Full Validation #69);

See `VALIDATION_COMMANDS.md`, `VALIDATION_REPORT_KO.md`, and `EXTERNAL_REVIEW_RESOLUTION_V2.6_KO.md`.

## Deployment status

**HARDENED SHADOW CANDIDATE.**

Do not promote to production merge-blocking ENFORCED until these external dependencies are demonstrated end to end:

1. OS-level network deny and workspace-only filesystem sandbox;
2. protected external runtime/human attestation issuers and key handling;
3. real L1/L2/Adversarial model workers and fresh-session issuance;
4. GitHub Check Run + required ruleset/branch-protection E2E;
5. production post-merge incident connector and sufficient calibration data;
6. Windows-specific path/process behavior and GUI/PyInstaller E2E where applicable.
