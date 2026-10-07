# CodeDiff 피드백 — R9A interpreter launch primitive / endpoint-policy coupling

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9A dedicated mediator candidate Windows closeout
- 분류: `ENVIRONMENT_INTERACTION / SEMANTIC_PORTABILITY_GAP`
- 상태: `OBSERVED → DESIGN REMEDIATION PREPARED`

## 관찰

R9A dedicated mediator EXE 자체의 build lineage는 Windows에서 성공했다.

하지만 mediator가 synthetic child를 시작할 때 공용 `powershell.exe`와 긴 `-EncodedCommand`를 launch
primitive로 사용했고, YM 환경에서는 child `Process.Start()`가 `Win32Exception`으로 차단됐다.

반환 evidence의 probe matrix는 다음 패턴을 보고했다.

- PowerShell parent + plain command: start 가능
- PowerShell parent + encoded command: start 가능
- unsigned dedicated EXE parent + plain command: start 가능
- unsigned dedicated EXE parent + 충분히 긴 encoded command: process creation 차단

이 패턴은 endpoint command-line policy와의 상호작용을 강하게 시사하지만, 특정 보안 제품/정책의 attribution은
검증되지 않았다.

따라서 현재 분류는 **environment interaction**이며 제품 defect 또는 특정 policy 이름으로 확정하지 않는다.

## 영향

- R9A build PASS는 유지된다.
- normal receipt는 생성되지 않았으므로 mediator runtime candidate PASS는 성립하지 않는다.
- stdout/stderr overflow 및 timeout negative test도 동일 child-launch primitive에 막혀 완결되지 않았다.
- `R9A_YM_EXECUTION_BLOCKED_ENVIRONMENT`가 가장 강한 결론이다.

## 권고

endpoint policy를 우회하는 방식으로 command line을 변형하지 않는다.

대신 synthetic child를 별도 **packaged helper executable**로 만든다.

권장 구조:

```text
DedicatedMediator.exe
  -> SyntheticChild.exe <short fixed mode>
```

helper EXE도 source/compiler/binary SHA lineage를 갖고, mediator는 exact helper binary SHA를 검증한 뒤 실행한다.

이렇게 하면:
- shared PowerShell interpreter 의존 제거
- long encoded-command dependency 제거
- parent PID / creation time / binary SHA evidence 유지
- stdout/stderr bounded concurrent drain과 timeout negative tests 유지
- environment policy를 우회하지 않고 그 정책에 맞는 실행 구조로 변경

## CodeDiff 관점

이번 finding은 changed-path/routing 문제가 아니라 **launch primitive와 endpoint execution policy의 runtime
interaction** 문제다.

CodeDiff는 해당 변경을 ADVERSARIAL/HUMAN review로 올릴 수 있지만, 실제 Windows에서의 command-line-policy
compatibility를 직접 발견하지는 못했다.

향후 environment-sensitive launch primitives를 사용하는 변경에는 sandbox execution evidence를 별도 gate로
요구하는 것이 적절하다.
