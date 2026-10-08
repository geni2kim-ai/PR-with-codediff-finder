# Leonardo Continuous Review Improvement Loop

## 목적

로컬의 실제 코딩량을 단순 생산량이 아니라 reviewer/sensor 개선용 backdata로 전환한다.

## 관측 대상

1. Sensor: diff/encoding/weakening detection 정확도
2. L1: 대량 리뷰 precision/recall/calibration
3. L2: L1 뒤집힘과 중요 결함 재검출률
4. Adversarial: 신규/상충/high-risk adjudication
5. Human: policy/standard/exception authority
6. Post-merge: 실제 회귀/장애

## 핵심 분석

- L1→최종 일치율
- L2→최종 일치율
- L1/L2 disagreement 뒤집힘 방향
- Adversarial이 L2를 뒤집은 비율
- 모델/프롬프트/정책 버전별 precision/recall
- failure family별 miss/false-positive rate
- TextDiff quality class별 실제 oracle 차이
- post-merge incident에서 어느 계층이 최초로 신호를 냈는지

## Standard evolution

새로운 케이스는 바로 standard가 되지 않는다.

```text
case
 → 재현/상위 adjudication
 → failure family
 → regression fixture
 → 반복성/중대성 확인
 → standard/check proposal
 → independent review
 → human/CODEOWNER approval
```

이 과정을 통해 동일한 실수를 반복해서 사람에게 지적받는 경우를 deterministic check 또는 명시적 standard로 이동시킨다.

## v2.7 material-aware calibration

v2.7에서는 low-severity anti-loop와 Leonardo calibration의 의미를 일치시킨다.

- L1 `FINDINGS`가 전부 NOTE_ONLY이면 calibration에서는 material state를 `PASS`로 본다.
- L1/L2 reversal도 raw verdict 문자열이 아니라 material finding state로 계산한다.
- HUMAN `CONFIRMED/REJECTED`는 L1/L2/ADVERSARIAL의 `PASS/FINDINGS`와 문자열 비교하지 않는다. HUMAN decision은 parent review 확인/거절 통계로 별도 집계한다.
- broad `failure_family` 하나만으로 동일 material issue를 판정하지 않는다. repeat key는 failure family + axis + path를 묶어 서로 다른 결함의 false repeat를 줄인다.
- 반복 NOTE는 자동 수정하거나 standard로 바로 승격하지 않는다. case 단위 반복 횟수를 집계해 `recurring_note_*` proposal signal로만 노출하고, 재현/상위 adjudication/HUMAN+CODEOWNER 절차를 그대로 요구한다.
- review campaign attempt/stop reason은 case backdata에 요약되어 `automated_attempts_p95`, `same_material_repeat_rate`, `review_budget_human_escalation_rate` 계산에 사용한다.

이로써 단기 anti-loop가 장기 calibration에서 다시 “L1 오답”으로 학습되는 역효과를 막는다.
