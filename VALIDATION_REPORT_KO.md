# GitHub PR Review Harness v2.6 검증 보고서

## 결과 요약

### Harness
- `tests.test_policy_engine`: **12 PASS**
- `tests.test_v22_integration`: **11 PASS**
- `tests.test_v23_orchestration`: **15 PASS** (method-isolated)
- `tests.test_v24_hardening`: **20 PASS**
- `tests.test_v25_dogfood`: **10 PASS**
- `tests.test_v26_hardening`: **20 PASS** (method-isolated)
- Harness 합계: **88 PASS / 39 isolated groups**

### TextDiffChecker
- vendored regression: **144 PASS**, GUI class **1 skip**
- `DIFF-FALSE-EXACT` fixture: PASS
- 작은 non-minimal deterministic 경로: `DETERMINISTIC`
- banded/patience fallback 경로: `HEURISTIC`

### Schema / semantic examples
다음 항목을 canonical runner에서 모두 PASS 확인했다.
- textdiff evidence
- case record
- review result
- RSI evaluation
- L1/L2/Adversarial task/result
- review cycle
- ledger chain / anchor
- case bundle
- adversarial packet
- adjudication
- standard candidate

### Static compile
`python -m compileall -q tools tests`: **PASS**

## v2.6 신규 반례 20개
1. canonical anchor 이름과 post-cycle human tool의 동일 anchor 사용.
2. HMAC anchor 무키 append downgrade 차단.
3. anchor 삭제 후 history 재시작 차단.
4. U+2028/U+2029/U+0085 payload가 ledger physical record를 깨지 않음.
5. infra/deploy/public API/migration HUMAN floor 강제.
6. `security_surface=HIGH` HUMAN floor 강제.
7. 실제 cycle이 HUMAN floor를 Adversarial에서 success로 닫지 못함.
8. harness 자체 `tools/tests/vendor` self-protection.
9. protected-path case-insensitive 매칭.
10. destructive migration deterministic signal 생성 및 HUMAN routing.
11. literal backslash Git filename에서 false-exact/0-line evidence 방지.
12. MODIFIED인데 blob identity가 빠진 evidence 거부.
13. form-feed로 test weakening 탐지 회피 불가.
14. 정상 코드 identifier URL 오탐 감소.
15. URL/reference host/credential/token/JWT/Bearer/DB URL 탐지 확대.
16. trusted tool pin 비어 있음 허용 금지.
17. 작은 diff의 DETERMINISTIC vs heuristic fallback 분리.
18. human confirmation이 cycle/ledger/head/attestation에 바인딩.
19. recomputed cycle digest 위조로 GitHub success render 불가.
20. worker timeout이 stdin write에서 막히지 않고 descendant process까지 종료.

추가 회귀로 random-audit reproducibility, ENFORCED에서 audit disable 금지, `python -m` module/cwd provenance binding을 확인했다.

## Canonical 실행 증거

```bash
python tools/run_validation.py --full --test-timeout 120
```

결과:
- return code: **0**
- `harness isolated tests: 88 PASS (groups=39, sequential)`
- `Ran 144 tests ... OK (skipped=1)`
- `vendored TextDiffChecker regressions + DIFF-FALSE-EXACT fixture: PASS`
- `ALL VALIDATIONS PASS (FULL)`

## NOT_RUN
- 실제 GitHub Check Run API + required ruleset/branch protection E2E
- 실제 OS network namespace/firewall/workspace-only filesystem isolation
- 실제 모델 worker와 외부 fresh-session issuer
- 실제 조직 IAM 기반 human identity issuer
- Windows process-tree/path semantics E2E
- Windows GUI/PyInstaller E2E
- production incident connector

## 판정
**HARDENED SHADOW CANDIDATE.** 코드/회귀 검증은 PASS지만 외부 인프라 전제가 남아 있으므로 ENFORCED production 승격을 스스로 승인하지 않는다.
