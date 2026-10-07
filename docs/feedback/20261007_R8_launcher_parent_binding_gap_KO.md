# CodeDiff 피드백 — R8 launcher parent-binding evidence gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R8 controlled-launcher synthetic rehearsal
- 분류: `EVIDENCE_GAP / SEMANTIC_REVIEW_GAP`
- 상태: `OPEN → LOCAL FIX PREPARED`

## 관찰

R8 receipt는 `System.Diagnostics.Process.Start`가 반환한 child PID를 사용하고, 해당 PID의 creation time,
executable path, SHA-256을 다시 읽어 일치시키는 데 성공했다.

하지만 receipt에는 OS가 관측한 child의 `ParentProcessId`가 launcher PID와 일치하는지에 대한 명시적
증거가 없다.

synthetic rehearsal에서는 API 호출 자체가 launcher의 child 생성 사실을 강하게 뒷받침하지만, 이후
mediated workload boundary로 확장할 때는 OS-observed parent binding을 함께 남기는 편이 더 강하다.

## 영향

- 현재 R8 synthetic PASS를 무효화하지는 않는다.
- 하지만 이후 launcher↔child lineage를 보안 경계로 사용하려면 parent relation evidence가 부족하다.
- direct finding은 semantic review에서 발견됐고 CodeDiff SHADOW는 이를 직접 탐지하지 못했다.

## 권고

R8.1에서 다음 필드를 추가한다.

- launcher PID
- OS-observed child ParentProcessId
- `parent_pid_matches_launcher=true`

그리고 evaluator는 mismatch를 fail-closed 처리한다.

예:

```text
CHILD_PARENT_PID_MISMATCH
```

## CodeDiff 관점

이번 finding은 changed-path/routing 문제가 아니라 process-lineage 의미론 문제다.

CodeDiff는 해당 변경을 높은 검토 단계로 올리는 역할은 했지만, child process lineage 증거 누락을 직접
발견하지는 못했다. direct defect discovery와 routing 성능을 계속 별도 측정하는 것이 적절하다.
