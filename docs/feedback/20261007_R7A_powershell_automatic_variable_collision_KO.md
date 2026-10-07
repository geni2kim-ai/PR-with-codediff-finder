# CodeDiff 실사용 피드백 — PowerShell automatic variable 충돌 미탐

- 날짜: 2026-10-07
- CodeDiff 코드 baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- 적용 work unit: `YM-R7A-ONE-REAL-WORKLOAD-DISCOVERY`
- 분류: `FALSE_NEGATIVE / STATIC_ANALYSIS_GAP`
- 상태: `LOCAL FIXED / UPSTREAM IMPROVEMENT CANDIDATE`
- authority effect: `NONE`

## 1. 관찰

R7A의 Windows PowerShell collector에서 다음 함수가 포함돼 있었다.

```powershell
function Get-Proc([int]$Pid) {
    return Get-CimInstance Win32_Process -Filter ("ProcessId=" + $Pid)
}
```

Windows PowerShell에서 `$PID`는 현재 PowerShell process ID를 나타내는 automatic variable이며 read-only다.
PowerShell 변수 이름은 대소문자를 구분하지 않으므로 `$Pid`도 같은 변수로 취급된다.

결과적으로 collector는 실제 측정 전에 parameter binding 단계에서 실패했다.

YM sandbox는 fail-closed 상태를 유지한 채 로컬 worktree copy에서 parameter만 다음처럼 바꿨다.

```powershell
function Get-Proc([int]$TargetPid) {
    return Get-CimInstance Win32_Process -Filter ("ProcessId=" + $TargetPid)
}
```

그 뒤 R7A read-only discovery가 정상 진행됐다.

## 2. 영향

- 기능 오류: collector가 시작 즉시 실패
- 보안 영향: fail-closed였으므로 잘못된 identity/authority 발급은 없음
- 운영 영향: packaged source를 그대로 실행할 수 없어 local patch가 필요
- 리뷰 영향: Python/static contract 테스트와 CodeDiff SHADOW routing에서는 이 PowerShell semantic defect를 잡지 못함

## 3. CodeDiff 관점

이 finding은 path/routing 문제가 아니라 **언어별 semantic lint gap**이다.

현재 CodeDiff가 잘 수행하는:
- changed-path inventory
- protected-path routing
- review escalation
- lineage

만으로는 다음 유형을 직접 잡기 어렵다.

- PowerShell automatic variable shadowing/collision
- reserved/read-only built-in variable assignment
- shell-specific parameter binding defects
- runtime-specific language semantics

## 4. 권고

### 4.1 PowerShell semantic sensor 추가

PowerShell 변경 파일에 대해 최소한 다음 automatic/read-only variable 이름과 parameter/local-variable 충돌을 검사할 수 있다.

예:

```text
PID
HOME
Host
Error
Input
Matches
MyInvocation
PSBoundParameters
PSScriptRoot
PSCommandPath
args
this
```

단순 regex만 사용하면 오탐이 있을 수 있으므로 가능하면 PowerShell AST 기반 검사를 권장한다.

예:

```powershell
[System.Management.Automation.Language.Parser]::ParseFile(...)
```

function parameter와 variable expression을 수집한 뒤 automatic variable set과 비교한다.

### 4.2 sensor 결과 분리

이 검사는 TextDiff 자체와 분리된 language-specific sensor로 두는 편이 좋다.

예:

```json
{
  "sensor": "powershell_semantic",
  "finding": "AUTOMATIC_VARIABLE_COLLISION",
  "symbol": "Pid",
  "built_in": "PID",
  "severity": "major"
}
```

### 4.3 CI fixture

최소 regression fixture:

```powershell
function Good([int]$TargetPid) { }
function Bad([int]$Pid) { }
```

기대:
- Good: no finding
- Bad: `POWERSHELL_AUTOMATIC_VARIABLE_COLLISION`

## 5. 성능 해석

이번 사례는 CodeDiff의 현재 역할 구분을 다시 확인한다.

CodeDiff는 해당 파일이 보안 경계에 속한다는 **routing**에는 도움이 됐지만,
실제 PowerShell runtime defect를 직접 발견하지는 못했다.

따라서 성능 지표에서도:

- risk routing 성공
- direct defect discovery 실패

를 별도로 기록하는 것이 맞다.

## 6. 로컬 상태

R7A 반환 패키지는 다음을 포함해 재현 가능하게 남겼다.

- 원본 collector
- 수정된 실제 사용 collector
- exact patch
- source SHA-256
- fail-closed 후 read-only 재실행 결과

수정은 parameter 이름 변경뿐이며 권한/인증 동작은 추가하지 않았다.

## 결론

PowerShell 코드가 포함된 프로젝트에서 CodeDiff를 사용한다면 diff/routing layer에 더해
**PowerShell AST 기반 automatic-variable collision sensor**를 추가할 가치가 있다.

이번 finding은 core diff algorithm defect라기보다 language-aware static analysis coverage gap으로 분류한다.
