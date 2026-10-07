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
3. anchor 삭제 후 history 재시작 차단, **ledger 0바이트 truncation + anchor 삭제 조합도 재시작 차단**.
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

## Post-review delta 검증

외부 검토를 다시 대조하는 과정에서 기존 ledger 파일을 **0바이트로 truncate한 뒤 anchor까지 삭제**하면 새 history처럼 재시작할 수 있는 잔여 반례를 추가로 발견해 차단했다.

최신 delta:
- `tools/case_ledger.py`: pre-existing ledger 파일은 이벤트가 0개로 보이더라도 anchor가 없으면 append 거부.
- `tests/test_v26_hardening.py`: 기존 HMAC/anchor 회귀에 zero-byte truncation 조합 추가.
- 최신 GitHub 파일 `tools/case_ledger.py` SHA-256: `8064dfdf923958452f85f50e4f3c3891f2c5a4d152ffd2b263da6cdca75b5958`.
- 동일 바이트의 파일을 별도 Python probe로 실행하여 `PASS_BLOCKED: existing ledger anchor missing` 재현 확인.

위의 **88 PASS / vendor 144 PASS** canonical full-run은 이 delta 이전 candidate에서 수행된 결과다. 최신 delta는 targeted execution으로 검증했으며, 현재 환경에서는 GitHub DNS가 차단되어 최신 branch 전체를 다시 clone해 full suite를 재실행하지 못했다. 따라서 merge/승격 전 최신 HEAD에서 canonical full-run을 한 번 더 수행해야 한다.

## NOT_RUN
- 실제 GitHub Check Run API + required ruleset/branch protection E2E
- 실제 OS network namespace/firewall/workspace-only filesystem isolation
- 실제 모델 worker와 외부 fresh-session issuer
- 실제 조직 IAM 기반 human identity issuer
- Windows process-tree/path semantics E2E
- Windows GUI/PyInstaller E2E
- production incident connector

## 판정
**HARDENED SHADOW CANDIDATE.** pre-delta canonical full-run과 post-delta targeted regression은 PASS다. 최신 HEAD 전체 full-run과 외부 인프라 전제가 남아 있으므로 ENFORCED production 승격이나 merge를 스스로 승인하지 않는다.
