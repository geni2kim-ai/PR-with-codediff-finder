# v2.7 코딩·리뷰 반복시간 시뮬레이션

## 목적

v2.7 소스를 실제로 코딩하고 리뷰/수정하는 상황을 가정해, finding 등급이 과하거나 부족하지 않은지와 자동 반복이 작업시간을 과도하게 늘리는지 점검한다.

기준 정책:
- reviewer timeout: 180초 / stage
- NOTE_ONLY: nit, minor
- major: 최소 L2
- blocker: 최소 ADVERSARIAL
- 자동 campaign: 최대 3 attempts
- 동일 material finding key 반복 한도: 완료된 material attempts 2회
- 완료된 material attempt의 retry: 새 HEAD 필수
- NOTE_ONLY/PASS 완료 후 자동 retry 금지

## 시뮬레이션 결과

| 상황 | 자동 경로 | 최대 worker stages | worker timeout budget | 판정 |
| --- | --- | ---: | ---: | --- |
| 오타·문구·스타일 | L1 → NOTE_ONLY → 종료 | 1 | 180초 (3분) | 적절 |
| 국소적 저영향 문제 | L1 → minor NOTE_ONLY → 종료 | 1 | 180초 (3분) | 적절 |
| 실제 기능 결함 | L1 major → L2 확인 → batched fix → 새 HEAD → L1 PASS | 3 누적 | 540초 (9분) | 적절 |
| 동일 major가 수정 후에도 남음 | 1차 L1+L2 → fix → 2차 L1+L2 → HUMAN | 4 누적 | 720초 (12분) | 자동루프 차단 |
| blocker/security/data/authority | L1 → L2 → ADVERSARIAL → HUMAN/상위권한 | 최대 3 | 540초 (9분) | 자동 수정 반복보다 상위 판단이 적절 |
| 수정 과정에서 서로 다른 major가 연속 발생 | 최대 3 attempts | 보통 최대 6, 절대 최대 9 | 보통 1,080초 (18분), 절대 1,620초 (27분) | 4번째 자동 반복 금지 |
| 완료된 결과를 같은 HEAD로 재실행 | 즉시 거부 | 0 추가 | 0 | 불필요한 반복 제거 |
| NOTE_ONLY를 지우려고 retry | 즉시 거부 | 0 추가 | 0 | 오타 무한루프 제거 |

## 등급 구분 평가

현재 4단계 severity는 유지하는 편이 낫다.

- `nit`: 오타, 문구, naming, formatting, cosmetic consistency. 실행/보안/테스트 영향 없음.
- `minor`: 국소적이고 가역적이며 backlog로 남겨도 안전한 저영향 문제.
- `major`: 실제 runtime correctness, 사용자 기능, 호환성, recovery/idempotency, test-integrity, supply-chain 등 closeout 전에 수정해야 할 문제.
- `blocker`: security/authority bypass, data loss/corruption, destructive/irreversible effect 등 release unsafe 문제.

등급 수를 더 늘리면 모델의 경계 판단 비용과 disagreement가 늘 수 있으므로, 별도 5단계보다 **4단계 severity + action disposition(NOTE_ONLY / AGENT_REVIEW_REQUIRED / BLOCKING)** 조합이 더 단순하다.

단, severity 오분류가 authority downgrade가 되지 않도록 `SECURITY-CRITICAL`, `DATA-CORRUPTION`, `GOVERNANCE*`, novel failure 및 deterministic/protected-path floors는 low severity보다 우선한다.

## 반복시간 병목 분석

기존 구조에서 가장 큰 시간 낭비는 finding 수가 아니라 **finding 하나씩 수정하고 HEAD를 계속 바꾸는 작업 방식**이다.

예를 들어 material finding 5개가 한 번에 발견됐을 때 각각 수정·push·CI·재검토를 하면 최대 5개의 새 HEAD와 5개의 review/CI 라운드가 생길 수 있다. 이를 한 remediation batch로 합치면 새 HEAD는 1개, 자동 재검토도 1회가 된다.

따라서 v2.7의 기본 운영 단위는:
1. 한 review attempt에서 findings 수집;
2. NOTE_ONLY는 기록만;
3. material findings를 한 번에 수정;
4. 하나의 remediation HEAD 생성;
5. 한 번 재검토;
6. 같은 문제가 반복되면 HUMAN, 새 문제가 생겨도 총 3 attempts에서 자동 종료.

## 보완 후 기대효과

- 오타 하나가 source edit를 유발하지 않으므로 typo loop가 구조적으로 끊긴다.
- 같은 major를 계속 자동 수정하는 loop는 2번째 완료 material attempt에서 끝난다.
- 다른 문제가 연속 발생해도 최대 3 attempts 이후 HUMAN/owner가 범위 재설정 여부를 판단한다.
- agent call과 CI가 finding 개수가 아니라 **remediation batch 수**에 비례한다.
- low-value 작업시간은 줄이면서 security/governance/test-integrity floor는 유지한다.

이 시뮬레이션은 자동 merge/HUMAN/ENFORCED 권한을 생성하지 않는다. 실제 calibration 데이터가 쌓이면 `automated_attempts_p95`, `same_finding_repeat_rate`, `note_only_rate`, `latency_p95`를 기준으로 attempt 한도를 조정한다.


## 실행 검증 결과

회귀 테스트로 시뮬레이션을 실제 실행했다.

- `test_budget_evaluator_bounds_same_and_new_material_findings`: PASS
- `test_material_retry_requires_changed_head`: PASS
- `test_note_only_closeout_cannot_start_retry_loop`: PASS
- `test_one_batched_fix_then_pass_closes_campaign`: PASS
- `test_same_material_finding_after_batched_fix_requires_human`: PASS

전체 canonical validation 결과는 **139 PASS / 81 isolated groups**, vendored TextDiffChecker **144 PASS / 1 GUI skip**, DIFF-FALSE-EXACT PASS였다.

시뮬레이션 도중 추가로 발견된 문제:
- review output directory가 repository 내부에 있을 때 2차 attempt가 1차 attempt 산출물을 untracked working-tree 변경으로 오인할 수 있었다.
- retry worktree 검사에서 현재 attempt만 제외하던 것을 campaign root 전체 제외로 수정했다.
- 이 문제는 retry 시뮬레이션 테스트가 직접 통과함으로써 재검증했다.

## calibration 제안

등급/시간 정책은 고정값으로 영구 유지하기보다 backdata로 조정한다. `policy/limits.yml` calibration 지표에 다음을 추가했다.

- `note_only_rate`
- `major_l2_downgrade_rate`
- `automated_attempts_p95`
- `same_material_repeat_rate`
- `review_budget_human_escalation_rate`

특히 `major_l2_downgrade_rate`가 높으면 L1이 사소한 문제를 major로 과대평가하는 신호이고, `same_material_repeat_rate`가 높으면 fix 품질이나 finding 설명 품질을 먼저 개선해야 한다.


## 등급 오분류 시뮬레이션 후속

severity 자체가 잘못 선택되는 상황도 추가로 시뮬레이션했다.

### SECURITY-CRITICAL인데 minor로 표기

기존 중간 구현:
- NOTE_ONLY로는 떨어지지 않았지만, 단순 `minor` severity 때문에 L2 강제가 완전히 보장되지 않았고 final gate도 raw severity를 보아 성공 처리될 여지가 있었다.

보완:
- semantic disposition이 `AGENT_REVIEW_REQUIRED`이면 severity와 무관하게 최소 L2.
- final gate는 major/blocker 문자열이 아니라 material finding 존재 여부로 실패 처리.

### test_integrity인데 minor로 표기

보완:
- `test_integrity` axis를 force-agent-review axis로 고정.
- minor/nit로 잘못 표기되어도 L2를 실행하고 material finding으로 처리.

실행 테스트:
- `critical-minor`: L1 → L2, required=L2, gate=failure.
- `test-integrity-minor`: L1 → L2, required=L2, gate=failure.
- 통합 회귀 `test_semantic_override_minor_requires_l2_and_cannot_gate_success_when_confirmed`: PASS.

따라서 현재 등급 체계의 핵심은 **severity label + semantic override + action disposition**이다. 4단계 severity를 더 세분화하는 것보다, 의미상 중요한 축/가족을 독립 authority signal로 유지하는 것이 오분류 비용과 반복시간을 동시에 줄인다.

최신 canonical 결과: **140 PASS / 82 isolated groups**, TextDiffChecker **144 PASS / 1 GUI skip**, full validation PASS.


## 미완료 상위검토 재개 시간 최적화

추가 시뮬레이션에서 `L1 완료 → L2 worker 부재 → WAITING_L2 → L2 연결 후 retry`를 재현했다.

기존 방식:
- retry 시 L1을 다시 실행한 뒤 L2를 실행.
- 같은 코드/같은 evidence를 다시 보는 데 최대 180초의 L1 worker budget이 중복될 수 있음.

보완 방식:
- SHADOW에서 exact same HEAD이고 prior task/result가 유효하며 evidence, reviewer provenance, policy/standards, changed paths, trusted refs가 동일할 때만 L1을 재사용.
- 새 attempt에서는 L2만 실제 실행.
- ENFORCED는 runtime/fresh-session authority 때문에 재사용하지 않음.

실측 회귀:
- counting L1 worker의 호출 횟수는 initial + resume 전체에서 **1회**.
- resume budget: `reused_agent_stages=1`, `executed_agent_stages=1`.
- 추가 worker timeout budget은 L2 **180초**만 계산.
- 전체 canonical: **141 PASS / 83 isolated groups**.

따라서 반복시간 제어는 세 층으로 구성된다:
1. NOTE_ONLY는 수정/retry하지 않는다.
2. material 수정은 한 batch/새 HEAD로 묶고 같은 material repeat는 HUMAN으로 끊는다.
3. 수정이 아니라 상위 authority worker의 늦은 가용성 때문에 재개하는 경우, 안전하게 검증 가능한 lower stage는 다시 실행하지 않는다.
