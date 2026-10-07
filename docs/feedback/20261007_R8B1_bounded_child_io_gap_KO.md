# CodeDiff 피드백 — R8B.1 unbounded child-output / dual-stream deadlock gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R8B.1 opaque child mediation closeout
- 분류: `SEMANTIC_REVIEW_GAP / RESOURCE_BOUNDARY_RISK`
- 상태: `OPEN → LOCAL REMEDIATION PREPARED`

## 관찰

R8B.1 synthetic mediator는 child stdout을 `MemoryStream.CopyTo()`로 끝까지 읽은 뒤 stderr를 읽는다.

91-byte synthetic payload에서는 정상 작동했지만, 향후 untrusted/opaque child에 같은 패턴을 적용하면 두 가지
문제가 생길 수 있다.

1. stdout 크기에 상한이 없어 child가 큰 출력을 내면 mediator memory를 과도하게 사용할 수 있다.
2. stdout과 stderr를 순차적으로 drain하면 child가 양쪽 pipe에 충분한 데이터를 쓰는 경우 backpressure에
   의해 교착될 수 있다.

## 영향

- 현재 R8B.1 synthetic PASS는 무효화하지 않는다.
- 실제/불신 child mediation으로 확대하기 전에는 blocker다.
- child output을 opaque bytes로 취급해도 resource boundary가 없으면 trust boundary가 완전하지 않다.

## 권고

R8B.2에서 다음을 추가한다.

- stdout maximum byte count
- stderr maximum byte count
- 초과 시 fail-closed
- stdout/stderr concurrent drain
- child execution timeout
- timeout/overflow 시 child termination
- receipt에는 raw output이 아니라 byte count/hash/status만 기록

권장 typed failures:

- `CHILD_STDOUT_LIMIT_EXCEEDED`
- `CHILD_STDERR_LIMIT_EXCEEDED`
- `CHILD_EXECUTION_TIMEOUT`

## CodeDiff 관점

이번 finding은 path/routing이나 structured-field filtering이 아니라 process I/O와 resource semantics의 문제다.
CodeDiff는 높은 검토 단계로 routing했지만 직접 탐지하지 못했다.
