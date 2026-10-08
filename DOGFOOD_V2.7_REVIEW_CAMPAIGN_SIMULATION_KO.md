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
