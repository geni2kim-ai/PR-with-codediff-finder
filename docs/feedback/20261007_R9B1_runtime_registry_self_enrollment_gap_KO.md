# CodeDiff 피드백 — R9B.1 runtime-generated verifier registry is not an independent trust anchor

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9B.1 local Named Pipe workload measurement closeout
- 분류: `TRUST_BOOTSTRAP_GAP / SEMANTIC_REVIEW_GAP`
- 상태: `OBSERVED → NEXT-WORK REMEDIATION REQUIRED`

## 관찰

R9B.1 Windows rehearsal itself succeeded.

- dedicated mediator connected as the Named Pipe client,
- verifier captured client PID via `GetNamedPipeClientProcessId`,
- process creation/path/SHA and impersonated SID were bound,
- result stayed `MEASURED_NOT_AUTHENTICATED / NOT_AUTHORIZED / NONE`.

그러나 `run_r9b1_measurement.ps1`는 measurement 직전에 전달된 `MediatorExe`의 SHA와 현재
Windows SID를 읽어 `local_verifier_registry.raw.json`를 즉석 생성한다.

즉 현재 registry는 사전에 승인된 verifier-side trust anchor가 아니라 **동일 rehearsal harness가 방금 본
binary/SID를 self-enroll한 local fixture**다.

따라서 R9B.1은 capture consistency와 verifier-derived label rehearsal은 증명하지만,
"이 binary/SID가 사전에 승인된 workload였다"는 독립적 provenance는 증명하지 않는다.

현재 문서가 `LOCAL_REHEARSAL_ONLY` 및 `MEASURED_NOT_AUTHENTICATED`로 제한하고 있으므로 R9B.1 PASS
자체를 무효화하지는 않는다.

## 영향

- R9B.1 measurement rehearsal: PASS 가능.
- live authentication/authorization trust anchor로 사용: 금지.
- runtime harness가 registry를 생성하는 구조에서 stable workload/node identity로 승격하면 self-enrollment
  문제가 발생한다.

## 권고

다음 단계에서 registry provisioning과 measurement execution을 분리한다.

권장 구조:

1. 별도 bounded provisioning 단계에서 expected mediator binary SHA + allowed SID + derived workload ID를 생성
2. registry 파일의 canonical digest를 계산
3. measurement runner는 registry를 **입력으로만** 받으며 생성/수정하지 않음
4. expected registry digest를 별도 pin으로 요구
5. runtime observed SHA/SID가 pinned registry의 정확히 한 entry와 일치해야 measurement ready
6. registry provenance가 외부 승인/credential과 결합되기 전까지 결과는 계속 `MEASURED_NOT_AUTHENTICATED`

## CodeDiff 관점

이번 finding은 diff/path 문제가 아니라 trust bootstrap semantics 문제다.

CodeDiff는 verifier/registry 관련 변경을 높은 review level로 routing할 수 있지만,
"registry가 독립 입력인가, 같은 실행이 자기 자신을 등록하는가"는 semantic review가 필요하다.

향후 registry/allowlist/approval-list 변경에는 **producer != subject-under-measurement** 또는 명시적인
rehearsal-only self-enrollment 표기를 검토 항목으로 추가하는 것이 좋다.
