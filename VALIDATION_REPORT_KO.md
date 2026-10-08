# GitHub PR Review Harness v2.7 검증 보고서

## 검수 기준

v2.7부터 저장소 기본 지침은 **Latest-HEAD review**다. 이전 리뷰/PASS는 newer HEAD에 자동 승계하지 않는다. 수정 또는 작업 재개 시 현재 committed HEAD와 changed-file set을 다시 확인하고, 코드·정책·trusted refs·manifest가 바뀌면 최신 HEAD를 재검수한다.

이번 v2.7 코드 경계의 기준 source HEAD는 `74abeeda337e3c76a1375c596b38d1e0928636ff`이다. 이 HEAD의 GitHub Actions Harness Full Validation **#223**에서 canonical full validation을 성공시켰다. 이후 closeout 단계의 문서/manifest 변경은 별도 PR 검증으로 다시 확인한다.

## 결과 요약

### Harness
- 자동 발견되는 `tests/test_*.py` 전체 포함
- v2.3 subprocess-sensitive 테스트는 기존 hard isolation 유지
- v2.6 hardening 테스트는 method isolation 유지
- v2.7 release/integrity 테스트 포함
- 합계: **122 PASS / 68 isolated groups**

### TextDiffChecker
- vendored regression: **144 PASS**
- GUI class: **1 skip** (Linux CI 환경)
- `DIFF-FALSE-EXACT` fixture: **PASS**

### Manifest
- source HEAD #223 push validation에서 generated manifest 적용 후 Git blob 검증: **PASS (229 entries)**
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
- `harness isolated tests: 122 PASS (groups=68, sequential)`
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
