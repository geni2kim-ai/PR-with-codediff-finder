# Review Authority Ladder

## 1. 목적

리뷰 결과와 리뷰 **권한 수준**을 분리한다. `PASS`는 결함 판단 결과이고, `L1/L2/ADVERSARIAL/HUMAN`은 그 판단이 어디까지 검증되었는지를 나타낸다.

## 2. 계층

| Level | 역할 | 일반 처리 | 최종 권한 |
|---|---|---|---|
| Sensor | TextDiff/deterministic evidence | 변경 사실·불변조건 | 없음 |
| L1 | 대량 1차 리뷰 | 일반 correctness/standards/spec/test | 제한적 |
| L2 | senior review | 저신뢰·중요·L1 재검증 | 제한적 |
| ADVERSARIAL | 독립 상위 reviewer | 이견, 신규 failure family, 보안/고위험, 반례 공격 | 제안/판정 근거 |
| HUMAN | Owner/CODEOWNER | 정책/스탠다드/예외/고위험 최종 결정 | 최종 |

## 3. 핵심 불변조건

- 이전 판정을 새 판정으로 덮어쓰지 않는다.
- L1이 맞고 L2가 틀릴 수 있으므로 모든 trail을 보존한다.
- reviewer는 자기 confidence를 높게 썼다는 이유로 필요한 검증 레벨을 낮출 수 없다.
- required level은 `policy/escalation-policy.yml`과 deterministic signals에서 harness가 계산한다.
- `analysis_status=PASS`라도 required level이 아직 충족되지 않았으면 gate는 `action_required`다.

## 4. Review state

```text
UNREVIEWED
 -> L1_REVIEWED
 -> L2_REVIEWED
 -> ADV_REQUIRED -> ADV_REVIEWED
 -> HUMAN_REQUIRED -> HUMAN_CONFIRMED

Any state + head change -> STALE
Missing evidence/policy -> BLOCKED
Closed/superseded -> ABANDONED
```

## 5. Adversarial queue 분류

- `critical/` — blocker, security critical, destructive/irreversible
- `disagreement/` — L1/L2 결론 또는 원인 충돌
- `low-confidence/` — 중요 축에서 confidence 부족
- `novel-pattern/` — 기존 failure family에 맞지 않는 신규 유형
- `governance/` — review/CI/CODEOWNERS/policy 변경
- `random-audit/` — correlated miss 탐지를 위한 샘플

각 bundle에는 original diff ref, TextDiff evidence, deterministic signals, L1/L2 결과, disagreement summary, standards/spec refs, test results, exact adjudication question을 포함한다.


## 6. Sensor-driven escalation
- `trusted_for_gate=false` or `APPROXIMATE` -> minimum L2.
- failed sensor invariant -> minimum ADVERSARIAL.
- `HEURISTIC` + auth/security/governance/human-floor/high-security -> minimum ADVERSARIAL.
- low-confidence encoding -> minimum L2; protected/high-risk combination may raise further.

## 7. Provenance
L2 and ADVERSARIAL reviews must use independent context. Every machine reviewer record binds model/version, prompt/skill/policy/standards digests, evidence digest, input digest and reviewed head SHA. HUMAN records use `model=null`.
