# CodeDiff 피드백 — R9A.2 process-info evidence should prefer native handle-bound APIs

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9A.2 instance-anchored process observation closeout
- 분류: `SEMANTIC_REVIEW_GAP / WINDOWS_PROCESS_EVIDENCE_RELIABILITY`
- 상태: `OBSERVED → ARCHITECTURAL REMEDIATION PREPARED`

## 관찰

R9A.2는 R9A.1에서 확인된 transient-empty WMI `ExecutablePath`를 보완하기 위해 PID + creation time을
anchor로 고정하고 WMI path를 bounded retry하도록 변경했다.

YM에서는 packaged source unchanged build가 다시 성공했지만 서로 다른 두 실행에서:

- matrix normal: `R9A2_CHILD_PATH_OBSERVATION_TIMEOUT`
- direct run: `R9A2_CHILD_STARTTIME_OBSERVATION_TIMEOUT`

이 발생했다.

별도 bounded diagnostic probes에서는 동등한 unsigned test process의 WMI row/path가 약 250–300 ms 후
resolve되고 .NET StartTime은 즉시 읽혔다.

따라서 단순 timeout 조정으로 설명하기 어려우며, **security evidence를 WMI/.NET property materialization
timing에 의존하는 방식이 해당 환경에서 충분히 deterministic하지 않다**고 보는 것이 안전하다.

## 영향

- R9A.2 build PASS는 유지된다.
- runtime receipt와 20/21/22 negative matrix는 미완료다.
- 가장 강한 결론은 `R9A2_YM_EXECUTION_BLOCKED_OBSERVATION_UNRELIABLE`이다.
- WMI timeout을 계속 늘려 PASS를 유도하는 것은 evidence quality를 개선하지 않는다.

## 권고

이미 `Process.Start()`가 제공한 실제 child process handle이 있으므로 process-instance security evidence는
가능한 한 **handle-bound native APIs**에서 직접 얻는다.

권장:

- `GetProcessId(handle)` → handle/PID 일치
- `GetProcessTimes(handle)` → creation time
- `QueryFullProcessImageName(handle)` → executable path
- parent PID는 documented Toolhelp process snapshot에서 PID를 조회하고, 조회 전후 handle creation time을
  재검증
- exact helper SHA 확인
- WMI/System.Management를 runtime evidence path에서 제거

이 구조는 전역 process-property provider가 materialize될 때까지 기다리는 대신, 이미 생성에 성공한 child의
kernel process handle을 evidence anchor로 사용한다.

## CodeDiff 관점

이번 finding은 diff/path 문제가 아니라 **Windows evidence-source selection** 문제다.

CodeDiff가 높은 review level로 routing하는 것만으로는 WMI/.NET observation instability를 알 수 없었다.
Windows process identity/lineage를 security evidence로 사용하는 코드에는 sandbox runtime evidence와 함께
"handle-bound source를 사용할 수 있는데 provider/property 기반 source에 의존하는가"를 별도 semantic review
항목으로 두는 것이 좋다.
