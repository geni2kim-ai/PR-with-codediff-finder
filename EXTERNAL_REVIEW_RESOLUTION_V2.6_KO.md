# GitHub PR Review Harness v2.5 외부 검토 → v2.6 처리표

| # | 재현 지적 | v2.6 처리 | 상태 |
|---|---|---|---|
| 1 | cycle 이후 도구 anchor 이름 불일치 | canonical `case-events.anchor.json`; human/outcome/incident/route/bundle 도구 동일 경로 사용 + append 전 검증 | 해결 |
| 2 | `human_floor_paths`가 실제 HUMAN을 강제하지 않음 | `derive_required_level()` hard floor + cycle 동일 엔진 사용; security HIGH 포함 회귀 | 해결 |
| 3 | harness 집행 코드 비보호 | 이 저장소 self-review에서 `tools/tests/vendor/requirements`를 governance/HUMAN 보호 | 해결 |
| 4 | HUMAN 확정 단계 없음 | signed human attestation, HEAD 재검증, `HUMAN_CONFIRMED/REJECTED`, ledger close 재바인딩 | 해결 |
| 5 | cycle digest 재계산으로 success 위조 | check renderer가 latest `CYCLE_CLOSED`의 digest/state/gate를 대조 | 해결 |
| 6 | backslash Git filename false-exact | Git exact path 보존, policy normalization 분리; 실제 변경 lines/diff 회귀 | 해결 |
| 7 | output safety 오탐/미탐 | prose bare-TLD 제거, ref fields host 검사; URL/zero-width/secret/token/JWT/Bearer/DB URI 확대 | 해결 |
| 8 | HMAC downgrade/anchor 삭제 | 기존 HMAC anchor에 키 없으면 append 거부; ledger event가 있는데 anchor가 없으면 거부 | 해결 |
| 9 | Unicode line separator로 ledger 손상 | JSONL physical separator를 LF로 고정 | 해결 |
| 10 | FF/NEL로 weakening 회피 | diff line parsing을 `split('\n')` 기준으로 변경 | 해결 |
| 11 | 보호 경로 case-sensitive | policy matching casefold 적용 | 해결 |
| 12 | sensor quality가 거의 항상 HEURISTIC | `DETERMINISTIC` class 추가; heuristic fallback 분리 | 해결 |
| 13 | stdin write가 timeout보다 먼저 block / child 생존 | file-backed stdin + running size monitor + process-tree kill | 해결 |
| 14 | 죽은 정책 어휘 | destructive migration/public contract/CODEOWNERS-ruleset/payment signals 생성, deterministic conflict/unresolved adversarial 연결 | 해결 |

## 낮은 우선순위 후속 처리
- trusted-tool pin은 빈 값도 mismatch 처리.
- random audit는 external seed + case/head/level로 재현 가능; ENFORCED disable 금지.
- calibration `review_due`는 누적 threshold 이상이면 true, completed windows 별도 기록.
- L2/Adversarial fresh-session은 signed runtime attestation에 포함.
- worker digest는 cwd와 `python -m` module source 포함.
- outcome/incident/human mutation은 pending snapshot 준비 → ledger append → replace 순서.
- `route_case` case-bank/queue target immutable; standards/test refs와 L1/L2 digest 포함.
- validation runner는 `tests/test_*.py` 자동 발견.
- reviewer prompt 표기는 “Harness v2.6 / wire schema 2.4”로 분리.

## 남는 외부 전제
OS sandbox, GitHub required-check E2E, 실제 모델 worker/fresh-session issuer, 조직 IAM human issuer, Windows E2E는 코드 패키지 밖의 통합 검증 범위다. 따라서 권장 상태는 계속 SHADOW이다.
