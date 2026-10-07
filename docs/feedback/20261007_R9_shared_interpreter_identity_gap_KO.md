# CodeDiff 피드백 — R9 shared interpreter workload identity ambiguity

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9 mediator authentication preparation
- 분류: `SEMANTIC_IDENTITY_GAP / AUTHENTICATION_DESIGN_RISK`
- 상태: `OPEN → DESIGN BLOCKER IDENTIFIED`

## 관찰

현재 controlled mediator prototype은 PowerShell script로 구현되어 있고 실제 OS process executable은
공용 `powershell.exe`다.

기존 workload proof가 주로 확인하는 값은 process executable path/hash, process instance, SID/service SID
등이다.

같은 사용자 SID에서 여러 PowerShell script가 동일 `powershell.exe`를 사용하면 executable path/hash만으로
"이 process가 정확히 해당 mediator script"라고 구분할 수 없다.

## 영향

- PowerShell mediator prototype을 그대로 authenticated workload principal로 승격하면 workload identity가
  shared interpreter identity와 섞일 수 있다.
- launcher source digest가 별도로 존재해도 OS process evidence와 직접 결합되지 않으면 strong binding이 아니다.
- current synthetic rehearsal에는 영향이 없지만 live mediator authentication의 blocker다.

## 권고

live authentication 전 다음 중 하나가 필요하다.

1. dedicated mediator executable with exact binary SHA binding
2. dedicated Windows service identity/service SID plus controlled executable binding
3. equivalent protected workload identity that is observable by the broker

script-hosted PowerShell은 rehearsal/tooling에는 사용할 수 있지만 node/workload principal로 직접 승격하지 않는
것이 안전하다.

## CodeDiff 관점

이번 finding은 diff/path 문제가 아니라 **OS-observable identity와 source-level component identity의 불일치**
문제다. 높은 review routing만으로는 직접 발견되지 않으므로 semantic identity review가 별도 필요하다.
