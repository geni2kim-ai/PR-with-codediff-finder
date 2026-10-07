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
