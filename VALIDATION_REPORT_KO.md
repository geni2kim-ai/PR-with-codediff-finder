# GitHub PR Review Harness v2.7 검증 보고서

## 검수 기준

v2.7부터 저장소 기본 지침은 **Latest-HEAD review**다. 이전 리뷰/PASS는 newer HEAD에 자동 승계하지 않는다. 수정 또는 작업 재개 시 현재 committed HEAD와 changed-file set을 다시 확인하고, 코드·정책·trusted refs·manifest가 바뀌면 최신 HEAD를 재검수한다.

이번 package-integrity 후속 검토의 기준 code-bearing source HEAD는 `9c2f0d04bbee5cfad92ad6b8373c4a6e7a0198c3`이다. 이 HEAD의 GitHub Actions Harness Full Validation **#270**에서 canonical full validation을 성공시켰다. 이후 closeout 문서/manifest 변경은 별도 PR clean-extract 검증으로 다시 확인한다.

## 결과 요약

### Harness
- 자동 발견되는 `tests/test_*.py` 전체 포함
- v2.3 subprocess-sensitive 테스트는 기존 hard isolation 유지
- v2.6 hardening 테스트는 method isolation 유지
- v2.7 release/integrity 테스트 포함
- 합계: **140 PASS / 82 isolated groups**

### TextDiffChecker
- vendored regression: **144 PASS**
- GUI class: **1 skip** (Linux CI 환경)
- `DIFF-FALSE-EXACT` fixture: **PASS**

### Manifest
- source HEAD #270 push validation에서 generated manifest 적용 후 Git blob 검증: **PASS (233 entries)**
- PR/manual 경로는 committed `MANIFEST.sha256`이 generated manifest와 byte-for-byte 일치해야 다음 단계로 진행하는 fail-closed 구조를 유지한다.

### Schema / semantic examples
canonical runner에서 다음 경로를 PASS 확인했다.
- textdiff evidence
- case record
- review result
- RSI evaluation
- reviewer task/stage result
- review cycle
- ledger chain / anchor
- case bundle
- adversarial packet
- adjudication
- standard candidate

### Canonical result
- `harness isolated tests: 140 PASS (groups=82, sequential)`
- `Ran 144 tests ... OK (skipped=1)`
- `vendored TextDiffChecker regressions + DIFF-FALSE-EXACT fixture: PASS`
- `ALL VALIDATIONS PASS (FULL)`

## v2.7 주요 재검증 항목

1. HUMAN attestation freshness는 신규 decision acceptance window로만 강제되고, 이미 ledger-bound로 확정된 historical proof는 시간 경과만으로 무효화되지 않는다.
2. HUMAN recovery transaction은 canonical digest + HUMAN authority-key HMAC + deterministic transaction ID에 바인딩된다.
3. ledger append는 exact pre-append ledger bytes와 next event를 묶은 recovery journal로 event-fsync / anchor-replace 중단 창을 복구한다.
4. dead ledger lock은 owner PID가 존재하지 않을 때 즉시 회수된다.
5. 동일 case_id의 case-bank 재사용은 current case/binding/evidence가 immutable snapshot과 일치해야 한다.
6. standards/spec/tests는 reviewer 실행 전 `trusted-inputs/`에 동결된다.
7. routing/escalation/protected-path/sensor policy는 `effective-policy/` snapshot에 고정되고 evidence recomputation/validation도 같은 snapshot을 사용한다.
8. sensor evidence의 `config_sha256`은 실제 사용한 effective sensor policy bytes에 바인딩된다.
9. privacy-safe mutation receipt는 logical name, pre/post SHA-256, equality와 pre-snapshot digest만 노출하고 path/content를 허용하지 않는다.
10. mutation receipt output이 source/spec/pre-snapshot과 충돌하면 fail-closed하며, receipt write는 atomic replace를 사용한다.
11. receipt semantic validator는 exact top-level/item allowlist, equality consistency, `all_unchanged`, `receipt_digest`를 검증한다.
12. repository working rules는 negative test가 의도한 failure branch까지 도달했는지 요구한다.
13. freshness rejection과 single-use replay prevention을 구분하고, literal status flags를 measured evidence로 승격하지 않으며, cleanup claim은 실제 claimed path를 증명하도록 기본 지침에 반영했다.

## v2.7 package-integrity 후속 재검증

1. 기존 `verify_manifest.py`는 Git object만 검증해 `.git` 없는 배포 ZIP 자체를 직접 검증할 수 없었다.
2. filesystem 검증 모드를 추가해 extracted tree의 missing/extra/hash mismatch를 fail-closed로 처리한다.
3. manifest 경로는 POSIX 상대경로만 허용하고 traversal/backslash ambiguity를 거부한다.
4. filesystem-root 검증에서 manifest는 verified root 내부의 regular file이어야 하며 symlink/out-of-root manifest를 허용하지 않는다.
5. PR/manual release path에서 ZIP을 clean extraction한 뒤 filesystem manifest 검증과 canonical full validation을 다시 실행한다.
6. source-package receipt는 exact HEAD, ZIP SHA-256, manifest SHA-256, manifest entry count 및 clean-extract/full-validation 상태를 묶는다.
7. receipt semantic validator는 schema와 같은 exact field/name/type 규칙을 적용하고 `authority_effect=NONE`을 유지한다.
8. HUMAN replay 문구는 구현보다 넓은 “global one-time nonce” 주장으로 읽히지 않도록 exact signed-attestation replay 범위로 정정했다.
9. tracked `.pytest_cache`, `__pycache__`, `*.pyc`, `*.pyo`가 source package에 봉인되지 않도록 package hygiene gate와 회귀 테스트를 추가했다.
10. `git archive --format=zip` clean-extract에서 vendor 텍스트 바이트가 Git blob과 달라지는 것을 실제 검출했고, package builder를 exact Git blob byte 기반 ZIP 생성기로 교체했다.
11. CRLF/LF 혼합 fixture를 ZIP에 넣어 Git blob bytes가 그대로 보존되는 회귀 테스트를 추가했다.

## v2.7 self-dogfood 후속

- baseline dogfood module: 10 PASS.
- live policy mutation after review no longer changes/fails downstream routing; route consumes frozen `effective-policy/`.
- live standards/spec/test mutation after review no longer enters the adversarial packet; route consumes frozen `trusted-inputs/`.
- corrupted case-bank refs are revalidated before recovery requeue and fail closed on mismatch.
- route-only refs remain supported when no reviewed frozen file exists, preventing the freeze fix from weakening legacy routing behavior.
- dogfood+fix regressions increased the harness suite to **129 PASS / 71 isolated groups**.

## 최신 외부 feedback 대조

`main`의 R9B.3/R9B.3.1 후속 review 문서도 closeout 중 확인했다.

- negative test false-coverage 교훈은 Latest-HEAD Review Policy에 반영했다.
- privacy-sensitive original immutability gap은 v2.7 mutation receipt로 일반화했다.
- freshness-window rejection은 replay prevention과 별도 claim으로 취급하도록 명시했다.
- 외부 R9B.3 Windows-specific run binding/process capture 요구는 이 harness 패키지의 자체 구현 범위를 넘어서는 integration evidence이며, v2.7의 ENFORCED 권한 근거로 사용하지 않는다.

## NOT_RUN / 외부 승격 게이트

- 실제 OS network deny + workspace-only filesystem sandbox E2E
- protected external runtime/human attestation issuer와 production key handling
- 실제 독립 L1/L2/Adversarial model worker + fresh-session issuance
- GitHub Check Run + required ruleset/branch protection production E2E
- production incident connector와 충분한 calibration data
- Windows-specific process tree/path semantics 및 GUI/PyInstaller E2E

## 판정

**HARDENED SHADOW CANDIDATE.**

v2.7 코어 source HEAD의 canonical full validation은 PASS했다. 최종 package는 committed manifest가 closeout HEAD와 일치하고 PR/manual full validation이 성공하여 동일 HEAD의 ZIP artifact가 생성된 뒤에만 validated package로 취급한다. 테스트 PASS만으로 merge, HUMAN 승인 또는 ENFORCED production 승격을 자체 승인하지 않는다.


## v2.7 finding-triage / anti-loop 후속

- `minor/nit`는 NOTE_ONLY로 분류되어 `review-notes.json`에 기록되고 같은 closeout에서 자동 수정하지 않는다.
- NOTE_ONLY reviewer escalation은 baseline risk일 때 억제되며, low-confidence/novel/test-integrity signals도 NOTE_ONLY finding 자체만으로 authority를 올리지 않는다.
- NOTE_ONLY L1 FINDINGS와 L2 PASS는 material disagreement가 아니며 downstream `route_case`에서도 다시 adversarial escalation으로 살아나지 않는다.
- `major`는 코드 하드플로어로 최소 L2, `blocker`는 최소 ADVERSARIAL을 요구하며 config로 하향할 수 없다.
- protected-path/risk/deterministic floors와 random audit는 finding triage와 독립적으로 유지된다.
- 최신 code-bearing validation: **140 PASS / 82 isolated groups**, TextDiffChecker **144 PASS / 1 GUI skip**, full validation PASS.


## v2.7 coding/review campaign simulation follow-up

Executable simulations were added for the development loop itself.

- NOTE_ONLY closeout refuses automated retry.
- A completed material-finding review refuses retry when HEAD is unchanged.
- One batched remediation followed by a clean L1 PASS closes the campaign.
- The same material finding key surviving the batched remediation makes the second completed material attempt `HUMAN_REQUIRED`.
- A pure budget evaluator verifies that different new material issues may use the remaining attempt budget, but the third worker-bearing attempt is the automated ceiling.
- Review output stored inside the repository no longer causes the next retry to fail as dirty merely because the previous attempt directory is untracked; the full campaign root is excluded from worktree-dirty checks.
- `review-budget.json` records attempt/stage/time ceiling and remediation retry eligibility.

Latest code-bearing validation after these changes:
- harness: **140 PASS / 82 isolated groups**
- vendored TextDiffChecker: **144 PASS / 1 GUI skip**
- DIFF-FALSE-EXACT: PASS
- canonical result: `ALL VALIDATIONS PASS (FULL)`

Time-model conclusion with the current 180-second reviewer timeout:
- NOTE_ONLY: 1 stage, 180-second worker ceiling;
- one major review + one clean post-fix L1: 3 cumulative stages, 540 seconds;
- same major surviving the fix: 4 cumulative stages, 720 seconds, then HUMAN;
- absolute campaign ceiling: 3 attempts × 3 stages × 180 seconds = 1,620 seconds before HUMAN/owner handling.

This bound is for reviewer workers only; CI/package validation remains additional, so the repository rules now require one remediation batch/HEAD rather than one HEAD per finding.


## semantic-importance severity review

The latest-HEAD review found one grading inconsistency after the campaign simulation:

- A finding such as `SECURITY-CRITICAL` could be marked `minor` by a reviewer.
- The earlier triage prevented it from becoming NOTE_ONLY, but the authority calculation did not independently guarantee L2 for every semantically material low-severity finding.
- The final gate also still inspected raw major/blocker severity, which could have allowed a semantically material minor finding to produce success after review.

Remediation:
- every `AGENT_REVIEW_REQUIRED` disposition now creates an `agent_review_candidate` signal with a non-downgradable L2 floor;
- `test_integrity` is a force-agent-review axis even when the model labels it minor/nit;
- the final gate uses `material_findings(...)`, not raw severity alone;
- `SECURITY-CRITICAL`, `DATA-CORRUPTION`, `GOVERNANCE*`, test-integrity and novel/deterministic authority signals therefore cannot be made cheap merely by a severity-label mistake.

Executable regression:
- `test_semantic_override_minor_requires_l2_and_cannot_gate_success_when_confirmed`: PASS for both critical-minor and test-integrity-minor.

Latest code-bearing validation:
- harness: **140 PASS / 82 isolated groups**
- vendored TextDiffChecker: **144 PASS / 1 GUI skip**
- DIFF-FALSE-EXACT: PASS
- `ALL VALIDATIONS PASS (FULL)`
