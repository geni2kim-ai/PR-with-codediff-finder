# CodeDiff 피드백 — R7C launcher discovery false-negative risk

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R7C controlled-launcher discovery
- 분류: `FALSE_NEGATIVE / SEMANTIC_DISCOVERY_GAP`
- 상태: `OPEN → LOCAL REMEDIATION PREPARED`

## 관찰

현재 R7C discovery는 controlled root의 파일을 filename regex로 먼저 거른 뒤, 그 candidate만 runtime
reference와 연결한다.

이 구조에서는 실제 runtime configuration이 controlled file을 참조하더라도 파일명이 heuristic 패턴에
맞지 않으면 candidate 단계에서 빠질 수 있다.

따라서 `candidate=0`을 시스템 전체의 controlled launcher 부재로 확대 해석하면 안 된다.

## 권고

discovery 순서를 다음처럼 바꾸는 것이 안전하다.

1. runtime reference에서 파일 경로 후보 추출
2. controlled-root containment 확인
3. referenced controlled file을 filename과 무관하게 candidate 등록
4. filename regex scan은 보조 heuristic으로만 사용

candidate source도 구분한다.

- `REFERENCE_BOUND`
- `DIRECT_RUNNING_EXECUTABLE`
- `NAME_HEURISTIC`

## CodeDiff 관점

이번 변경은 CodeDiff가 높은 검토 단계로 routing한 것은 적절했지만, 실제 semantic coverage gap은 직접
발견하지 못했다.

따라서 direct finding과 review routing 성능을 계속 분리 측정하는 것이 좋다.
