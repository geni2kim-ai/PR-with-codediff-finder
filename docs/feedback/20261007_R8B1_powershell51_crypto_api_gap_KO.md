# CodeDiff 피드백 — R8B.1 PowerShell 5.1 crypto API portability gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R8B.1 opaque child mediation
- 분류: `PORTABILITY_GAP / SEMANTIC_REVIEW_GAP`
- 상태: `OPEN → LOCAL FIX PREPARED`

## 관찰

R8B.1 초안은 byte payload SHA-256을 계산할 때 다음 최신 .NET API를 사용했다.

- `Convert.ToHexString`
- `SHA256.HashData`

하지만 YM 실행 환경은 Windows PowerShell 5.1이며, 이 환경은 일반적으로 .NET Framework 기반이라 위 API가
보장되지 않는다.

따라서 Linux/Python static test는 통과해도 실제 Windows PowerShell 5.1에서 runtime failure가 날 수 있다.

## 영향

- packaged R8B.1 Windows rehearsal이 시작 후 hash 계산 지점에서 실패할 수 있음
- 기능상 fail-closed이지만 불필요한 local patch를 유발
- CodeDiff routing은 높은 검토 단계로 올렸지만 runtime API compatibility를 직접 탐지하지 못함

## 권고

PowerShell 5.1 호환 API로 제한한다.

예:

```powershell
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
  $digest = $sha.ComputeHash($bytes)
  $hex = ([BitConverter]::ToString($digest)).Replace("-","").ToLowerInvariant()
} finally {
  $sha.Dispose()
}
```

또한 static regression에서 `ToHexString`과 `HashData(` 사용을 금지한다.

## CodeDiff 관점

이 사례는 source diff만으로는 놓치기 쉬운 **runtime-version compatibility** 문제다.
Windows PowerShell 5.1을 지원 대상으로 명시한 프로젝트라면 language/runtime compatibility sensor가 별도로
필요하다.
