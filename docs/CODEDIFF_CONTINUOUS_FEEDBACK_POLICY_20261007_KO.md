# CodeDiff 지속 피드백 기록 규칙

- 대상 저장소: `geni2kim-ai/PR-with-codediff-finder`
- 적용 시작일: 2026-10-07
- 상태: ACTIVE

## 목적

PR-with-codediff-finder를 실제 코드 작업에 병행 적용하면서 새로 발견되는 문제와 개선점을 턴 단위로 잃지 않고 축적한다.

## 기록 규칙

각 작업 턴에서 CodeDiff와 관련해 **새로운 발견이 하나 이상 있을 때만** GitHub 문서를 남긴다.

새로운 발견의 범위:

- 도구 자체 결함
- 재현성 문제
- 환경 제약
- 오탐(false positive)
- 누락/미탐(false negative)
- protected-path / routing 분류 문제
- 성능/확장성 문제
- evidence / lineage 문제
- 패키징/배포 문제
- integration 문제
- usability 문제
- 기존 문제의 새로운 재현 조건
- 기존 권고의 실제 효과/실패
- 성능 측정 결과

새 발견이 없으면 문서를 억지로 생성하지 않는다.

## 문서에 반드시 포함할 항목

1. 기준 CodeDiff 버전/commit
2. 적용 대상 작업/work unit
3. 관찰된 현상
4. 재현 조건
5. 분류
   - TOOL_DEFECT
   - ENVIRONMENT_LIMITATION
   - FALSE_POSITIVE
   - FALSE_NEGATIVE
   - INTEGRATION_GAP
   - PACKAGING_GAP
   - POLICY_GAP
   - EVIDENCE_GAP
   - PERFORMANCE_OBSERVATION
6. 영향
7. 권고/보완 방향
8. 현재 상태
   - OPEN
   - MITIGATED
   - FIXED
   - NEEDS_UPSTREAM_CHANGE
   - OBSERVATION_ONLY
9. 관련 evidence/log/commit SHA

## 권장 파일명

```text
docs/feedback/YYYYMMDD_<work-unit>_codediff_feedback_KO.md
```

같은 work unit에서 연속 보완이 발생하면:

```text
docs/feedback/YYYYMMDD_<work-unit>_codediff_feedback_r2_KO.md
docs/feedback/YYYYMMDD_<work-unit>_codediff_feedback_r3_KO.md
```

## 운영 원칙

- CodeDiff는 승인자가 아니라 sensor / risk router / evidence generator로 취급한다.
- CodeDiff가 스스로 자기 변경을 최종 승인하게 하지 않는다.
- degraded sensor 결과는 trusted 결과로 승격하지 않는다.
- 환경 문제를 tool defect로 잘못 분류하지 않는다.
- integration 측 실수도 숨기지 않고 별도 분류로 남긴다.
- 발견이 후속 버전에서 해결됐으면 원문을 지우지 않고 상태를 FIXED/MITIGATED로 갱신하거나 후속 문서에서 연결한다.
- 각 결과 패키지에는 해당 턴의 CodeDiff usage/problem log를 계속 포함한다.

## 현재 기준 baseline

2026-10-07 기준 실사용 baseline:

- version: `2.5`
- commit: `69978ff50bc4003d6d73b8219790106846220f72`

baseline이 변경되면 이후 피드백 문서에 새 SHA를 명시한다.
