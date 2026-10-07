# CodeDiff 피드백 — test artifact pollution 재발

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R8.1 parent-bound launcher + R8B mediated boundary prep
- 분류: `INTEGRATION_GAP / REVIEW_EVIDENCE_POLLUTION`
- 상태: `LOCAL FIX REQUIRED`

## 관찰

후속 테스트를 실행한 뒤 임시 Git comparison tree를 그대로 stage하면서
`__pycache__/*.pyc` 파일들이 diff inventory에 포함됐다.

그 결과 실제 source 변경보다 훨씬 많은 파일이 CodeDiff 변경으로 집계됐다.

배포 ZIP에서는 pycache를 제외했지만, CodeDiff review evidence 자체는 오염된 상태였다.

## 영향

- changed-file count 과대계상
- protected-path hit 과대계상
- review noise 증가
- 실제 source delta와 generated artifact를 구분하기 어려움

## 권고

CodeDiff 실행 직전 integration harness에서 다음을 강제하는 것이 좋다.

1. generated cache/artifact 제거
2. `.gitignore` 또는 explicit exclude 확인
3. dirty-tree inventory에서 generated artifact가 발견되면 review 시작 전에 BLOCK
4. diff evidence에 generated-artifact count를 별도 기록

예시 차단 상태:

`REVIEW_TREE_GENERATED_ARTIFACTS_PRESENT`

## CodeDiff 관점

core diff algorithm 문제는 아니다.

하지만 반복 자동 리뷰 환경에서는 test execution이 candidate tree를 오염시키는 일이 자주 발생하므로,
review harness가 이를 자동으로 감지해 주는 것이 유용하다.

이번 R8.1 package는 pycache를 제거한 뒤 CodeDiff를 다시 실행해 evidence를 재생성한다.
