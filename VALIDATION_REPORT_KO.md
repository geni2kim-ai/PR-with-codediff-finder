# GitHub PR Review Harness v2.5 검증 보고서

## 결과 요약

### Harness
- `tests.test_policy_engine`: **12 PASS**
- `tests.test_v22_integration`: **11 PASS**
- `tests.test_v23_orchestration`: **15 PASS** (method-isolated 확인)
- `tests.test_v24_hardening`: **20 PASS**
- `tests.test_v25_dogfood`: **10 PASS**
- Harness 합계: **68 PASS**

### TextDiffChecker
- vendored regression: **144 PASS**, GUI class **1 skip**
- `DIFF-FALSE-EXACT` fixture: PASS

### Schema / semantic examples
- textdiff evidence: PASS
- case record: PASS
- review result: PASS
- RSI evaluation: PASS
- L1/L2/Adversarial task/result: PASS
- review cycle: PASS
- ledger chain/anchor: PASS
- case bundle: PASS
- adversarial packet: PASS
- adjudication: PASS
- standard candidate: PASS

## v2.5 신규 반례
1. runtime attestation case/base/head binding 및 stale rejection.
2. worker environment가 unverified sandbox를 주장하지 않음.
3. 리뷰 중 base ref 이동 → `STALE`.
4. worker script byte 변경 → `worker_command_digest` 변경.
5. secret-like environment allowlist 차단.
6. ENFORCED valid attestation provenance가 task/ledger에 연결됨.
7. ENFORCED stale attestation 차단.
8. `RUNTIME_ATTESTED` event가 ledger schema와 정합됨.
9. ENFORCED runtime attestation nonce 재사용 → `BLOCKED` (`ENFORCED_ATTESTATION_REPLAYED`).
10. ignored Python bytecode/cache가 review worktree dirty 신호를 만들지 않음.

## Dogfood 검증
v2.5 개발 변경을 v2.4 stable baseline으로 개발 중 반복 SHADOW review했다. 최종 실행 코드 commit `864ef63` 전체 diff는 **25 files / 1006 changed lines**, `HEURISTIC`, `trusted_for_gate=true`였고 protected policy/schema 경로 때문에 `HUMAN_REQUIRED / action_required`가 유지됐다. stable cycle의 reviewer는 deterministic mock PASS worker이므로 이 결과는 **authority routing / governance floor 검증**이며 실제 상위 모델의 의미론적 코드 승인을 뜻하지 않는다. candidate 자체 PASS가 stable authority floor를 낮추지 못했다.

## 실행 범위 주의
최종 후보에서 `python tools/run_validation.py --full --test-timeout 90`을 직접 실행했고 **return code 0**을 확인했다. test enumeration과 실행을 부모 프로세스에서 분리하고 각 group 종료 후 잔여 descendant process group을 정리해 multiprocessing 자기 간섭을 제거했다. 출력은 `harness isolated tests: 68 PASS`, `Ran 144 tests ... OK (skipped=1)`, `ALL VALIDATIONS PASS (FULL)`이었다.

## NOT_RUN
- 실제 GitHub Check Run / required ruleset / branch protection E2E
- 실제 OS network namespace/firewall/workspace-only filesystem isolation
- 실제 L1/L2/Adversarial 모델 worker 및 external fresh-session issuer
- Windows GUI/PyInstaller E2E
- production post-merge incident connector

## 판정
**HARDENED SHADOW / DOGFOOD CANDIDATE.** ENFORCED 전환 증거는 아직 부족하다.
