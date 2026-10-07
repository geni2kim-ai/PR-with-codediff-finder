# CodeDiff 피드백 — R9A.3 matrix runner expected-nonzero evidence capture gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9A.3 native-handle matrix closeout
- 분류: `INTEGRATION_GAP / EVIDENCE_CAPTURE_GAP`
- 상태: `OBSERVED → LOCAL FIX PREPARED`

## 관찰

R9A.3 mediator 자체는 YM에서 정상 case exit 0과 negative 20/21/22를 모두 재현했다.

하지만 packaged `run_r9a3_matrix.ps1`는 expected-nonzero native process invocation 뒤에
`exitcode.txt`를 기록해야 하는 구조인데, YM의 PowerShell native-command error semantics에서는
negative process가 nonzero를 반환하는 시점에 runner가 중단되어 증적 파일 기록까지 도달하지 못했다.

YM은 packaged source를 수정하지 않고 동일 binary/args/file layout을 `cmd.exe` redirection으로 실행해
20/21/22를 보존했다.

따라서 mediator negative behavior는 PASS지만 packaged matrix harness는 독립적으로 보완이 필요하다.

## 영향

- R9A.3 native-handle mediator의 0/20/21/22 동작 자체는 재현됨.
- packaged runner만으로는 expected-nonzero evidence capture가 portable하지 않음.
- harness workaround가 필요했으므로 다음 단계 package에서 그대로 재사용해서는 안 됨.

## 권고

PowerShell의 native-command error preference에 의존하지 않고 `System.Diagnostics.Process`로
child harness process를 실행한다.

runner가 직접:
- stdout/stderr capture
- exact ExitCode
- timeout
- receipt presence/absence
를 판정하도록 한다.

`$ErrorActionPreference` 또는 host별 `PSNativeCommandUseErrorActionPreference` semantics에 기대지 않는다.

## CodeDiff 관점

이 finding은 mediator source의 security semantics가 아니라 test/evidence harness portability 문제다.
CodeDiff는 높은 review level로 올렸지만 shell runtime behavior를 직접 검출하지 못했다.
