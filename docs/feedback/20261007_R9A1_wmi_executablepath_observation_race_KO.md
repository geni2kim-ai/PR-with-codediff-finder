# CodeDiff 피드백 — R9A.1 immediate WMI ExecutablePath observation race

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9A.1 packaged synthetic-child helper Windows closeout
- 분류: `SEMANTIC_REVIEW_GAP / WINDOWS_OBSERVATION_RACE`
- 상태: `OBSERVED → LOCAL REMEDIATION PREPARED`

## 관찰

R9A.1에서는 이전의 PowerShell encoded-command launch primitive를 제거하고 별도 packaged helper EXE를
직접 실행했다.

YM에서 두 바이너리는 unchanged source로 정상 빌드되었고 helper 자체 standalone 실행도 성공했다.
그러나 mediator가 helper를 `Process.Start()`로 시작한 직후 첫 WMI `Win32_Process.ExecutablePath`
조회가 빈 문자열을 반환했다.

packaged mediator는 빈 문자열을 즉시 `R9A1_CHILD_PATH_MISMATCH`로 처리해 fail-closed 종료했다.

YM replication에서는:
- immediate WMI ExecutablePath: empty
- 약 300 ms 후 WMI ExecutablePath: resolved
- .NET Process/MainModule path: resolved
- same packaged helper standalone: exit 0

따라서 현재 evidence는 process-creation failure가 아니라 **OS observation timing race**를 가리킨다.

## 영향

- R9A.1 build PASS는 유지된다.
- normal receipt는 생성되지 않았으므로 runtime candidate PASS는 성립하지 않는다.
- matrix가 첫 normal case에서 멈춰 20/21/22 negative runs는 NOT_RUN이다.
- 가장 강한 결론은 `R9A1_YM_EXECUTION_BLOCKED_OBSERVATION_RACE`다.

## 권고

단순 고정 sleep으로 완화하지 않는다.

권장 순서:

1. `Process.Start()`가 반환한 child PID 확보
2. child creation time을 먼저 읽어 process instance anchor 생성
3. parent PID를 확인
4. WMI ExecutablePath가 empty/null이면 bounded retry/backoff
5. retry 사이마다 PID가 여전히 존재하고 creation time이 동일한지 확인
6. path가 resolve되면 expected helper path + SHA 확인
7. retry budget 내 resolve되지 않으면 typed fail-closed

예시 typed failure:

`R9A2_CHILD_PATH_OBSERVATION_TIMEOUT`

이 방식은 PID reuse 또는 다른 process로의 관측 전이를 막으면서 transient WMI initialization만 흡수한다.

## CodeDiff 관점

이번 finding은 source path/routing 문제가 아니라 Windows process-observation semantics 문제다.

CodeDiff는 변경을 높은 review 단계로 올릴 수 있지만, 실제 WMI property materialization timing은 sandbox
execution evidence 없이는 직접 발견하기 어렵다.

Windows process lineage를 security evidence로 사용하는 변경에는 bounded observation retry + instance
revalidation test를 별도 gate로 두는 것이 적절하다.
