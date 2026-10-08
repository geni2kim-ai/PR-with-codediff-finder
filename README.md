# GitHub / Local PR Review Harness v2.7

v2.7 is the interruption/recovery hardening release built on the reviewed v2.6 candidate. It preserves the v2.6 authority/ledger/sensor/runtime protections and closes crash-recovery, immutable-state reuse, and trusted-input/policy TOCTOU gaps found by reviewing the latest post-fix HEAD.

> Package version: **2.7**  
> Wire compatibility: reviewer/task/evidence/event JSON objects intentionally retain the established `schema_version: "2.4"` wire contracts unless a specific v2.7 runtime/policy document says otherwise.

```text
reviewed v2.6 hardening baseline
        ↓
candidate v2.7
        ↓
TextDiff evidence
        ↓
L1 → L2 → Adversarial → Human
        ↓
anchored Case Bank + outcome/incident feedback
        ↓
Leonardo/Davinchi calibration / regression / standards loop
```

## v2.7 hardening highlights

- **Privacy-safe mutation receipts**: `tools/mutation_receipt.py` emits logical name + pre/post SHA-256 + equality only, without source paths/content, and fixes `authority_effect=NONE`.
- **Clean-extract source-package verification**: `verify_manifest.py --filesystem-root` verifies the delivered tree without `.git`, rejects missing/extra/tampered files and unsafe manifest paths, and CI reruns canonical validation from the extracted ZIP.
- **External source-package receipt**: the distributed ZIP is bound to exact HEAD, ZIP SHA-256, manifest SHA-256 and manifest entry count with `authority_effect=NONE`.
- **Latest-HEAD review is a repository default**: every review/resume refreshes the current committed HEAD; changes invalidate earlier closeout until the post-fix HEAD is reviewed again.
- **Crash-safe ledger append recovery**: an authenticated journal binds the exact pre-append ledger bytes, hash chain and next event so a crash between event fsync and anchor replacement can recover idempotently.
- **Dead-lock recovery**: ledger locks record owner PID and are reclaimed immediately when the owner process no longer exists.
- **HUMAN recovery transaction authentication**: recovery state is bound by canonical digest, HUMAN authority-key HMAC, source cycle/evidence/HEAD and recomputed transaction ID.
- **Historical HUMAN proof remains verifiable**: freshness is an acceptance-time rule; an already accepted ledger-bound HUMAN decision does not expire merely because time passed.
- **Immutable case-bank collision checks**: reuse of an existing case ID requires the current case, binding and evidence digest to match the stored immutable snapshot.
- **Trusted-input freeze**: standards/spec/tests are copied into `trusted-inputs/` before reviewer execution.
- **Effective-policy freeze**: routing/escalation/protected-path/sensor decisions, reviewer provenance, evidence recomputation and evidence validation use the same `effective-policy/` snapshot.
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

Keep the prior stable reviewer frozen while reviewing a candidate release. After v2.7 is independently accepted, it can become the next stable SHADOW baseline.

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

## Privacy-safe mutation receipt

For evidence-only closure where raw artifacts must remain local, keep a local-only spec containing logical names and paths, capture a pre-run digest snapshot, then finalize after the closure work. The distributable receipt contains no source path or content and has `authority_effect=NONE`.

```bash
python tools/mutation_receipt.py capture \
  --spec /local-only/artifacts.json \
  --output /local-only/pre-snapshot.json

python tools/mutation_receipt.py finalize \
  --pre /local-only/pre-snapshot.json \
  --spec /local-only/artifacts.json \
  --output /distributable/mutation-receipt.json

python tools/mutation_receipt.py validate \
  --receipt /distributable/mutation-receipt.json
```

The final receipt binds `pre_snapshot_digest`, per-artifact pre/post SHA-256 and equality. Preserve or externally anchor the pre-snapshot before mutation when stronger independent chronology is required.

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

`record_human_decision.py` no longer accepts an unauthenticated self-declaration. The current HEAD, anchored cycle and an external HMAC-backed human-decision attestation must agree. The replay cache is external authority state: configure one shared cache outside the mutable case bundle and do not vary it per invocation. It prevents reuse of the same signed attestation token; it is not claimed as a global nonce registry across differently signed contexts.

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

The v2.7 attestation binds workspace, case/base/head, sandbox assertions, freshness nonce/timestamp, plus external claims that the L2 and Adversarial sessions are fresh. These fresh-session claims are **fail-closed by default**: the launcher must explicitly assert them.

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

- harness: **124 PASS** across 68 isolated groups;
- vendored TextDiffChecker: **144 PASS, 1 GUI skip** in this Linux environment;
- DIFF-FALSE-EXACT fixture: PASS;
- schema/semantic examples, review cycle, ledger anchor, case bundle, packet, adjudication and standard candidate: PASS;
- v2.7 package-integrity follow-up code-bearing validation: **SUCCESS** (Harness Full Validation #270, source HEAD `9c2f0d04bbee5cfad92ad6b8373c4a6e7a0198c3`);
- final manifest/PR packaging validation is required on the closeout HEAD before the package is treated as validated.

See `VALIDATION_COMMANDS.md`, `VALIDATION_REPORT_KO.md`, and `EXTERNAL_REVIEW_RESOLUTION_V2.7_KO.md`.

## Validated source package

The GitHub Actions workflow creates `PR-with-codediff-finder-v2.7.zip` from the exact validated `HEAD` only on PR/manual runs where the committed manifest has already been verified and canonical full validation succeeds. CI then extracts the ZIP, verifies the extracted filesystem against `MANIFEST.sha256` without Git metadata, reruns canonical full validation from that extracted tree, creates `PR-with-codediff-finder-v2.7.receipt.json`, verifies the receipt, and uploads the ZIP + receipt together as the `v2.7-source-package` artifact. The receipt binds exact HEAD, ZIP SHA-256, manifest SHA-256 and manifest entry count; `authority_effect` remains `NONE`.

After download/extraction, the package tree can be checked without a Git repository:

```bash
python tools/verify_manifest.py --filesystem-root /path/to/PR-with-codediff-finder-v2.7

python tools/source_package_receipt.py validate \
  --receipt /path/to/PR-with-codediff-finder-v2.7.receipt.json \
  --package /path/to/PR-with-codediff-finder-v2.7.zip \
  --manifest /path/to/PR-with-codediff-finder-v2.7/MANIFEST.sha256
```


## Deployment status

**HARDENED SHADOW CANDIDATE.**

Do not promote to production merge-blocking ENFORCED until these external dependencies are demonstrated end to end:

1. OS-level network deny and workspace-only filesystem sandbox;
2. protected external runtime/human attestation issuers and key handling;
3. real L1/L2/Adversarial model workers and fresh-session issuance;
4. GitHub Check Run + required ruleset/branch-protection E2E;
5. production post-merge incident connector and sufficient calibration data;
6. Windows-specific path/process behavior and GUI/PyInstaller E2E where applicable.
