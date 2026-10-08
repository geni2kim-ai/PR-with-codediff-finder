# v2.7 Self-Dogfood + Improvement Report

## 기준

- 대상: `hardening/v2.7`
- 시작 기준 HEAD: `b0c61cec039c00a1eb77062c069df2781996d7cf`
- 방식: 기존 PASS를 승계하지 않고 최신 HEAD/배포 ZIP을 기준으로 정상 흐름과 중단·변조·재개 경계를 직접 재현한 뒤, 재현된 문제를 즉시 코드/회귀 테스트에 반영한다.
- 권한: dogfood PASS는 merge/HUMAN/ENFORCED 승격 권한을 만들지 않는다.

## baseline dogfood

최종 v2.7 package를 clean extraction한 뒤 기존 dogfood module을 직접 실행했다.

- `tests.test_v25_dogfood`: **10 PASS**
- runtime attestation context/expiry
- sandbox claim boundary
- base-ref move → STALE
- worker provenance
- secret env stripping
- ENFORCED attestation binding
- stale attestation rejection
- runtime attestation replay rejection
- ignored Python bytecode workspace handling

## 추가 dogfood 시나리오와 발견사항

### DF27-01 — route 단계 live-policy 재참조

재현:
1. review cycle 완료 후 `out/effective-policy/`가 존재함을 확인.
2. cycle 종료 뒤 live `policy/protected-paths.yml`만 변경.
3. 같은 완료 case를 `route_case.py`로 routing.

기존 결과:
- `L1 case trail effective policy digest mismatch`로 routing 실패.
- review에서 동결한 policy snapshot이 있음에도 downstream route가 live policy에 다시 의존.

보완:
- route는 cycle의 `effective-policy/`를 우선 authority로 사용.
- evidence semantic validation, policy digest, packet policy freeze 모두 동일 snapshot 사용.
- explicit routing override가 frozen routing policy와 다르면 fail-closed.

### DF27-02 — trusted standards/spec/test TOCTOU

재현:
1. standards/spec/test와 함께 review cycle 완료.
2. cycle이 `trusted-inputs/`에 원본을 동결한 뒤 외부 원본 세 파일을 변경.
3. 변경된 live 경로를 다시 `route_case.py`에 전달.

기존 결과:
- adversarial packet에는 review 당시 원본이 아니라 **변경된 live standards/spec/test**가 복사됨.
- L1 review의 standards provenance와 packet의 trusted input bytes가 달라짐.

보완:
- `trusted-inputs/`가 있는 v2.7 cycle은 route에서 그 snapshot만 사용.
- L1/L2 `standards_digest`를 frozen standards에 대해 재검증.
- legacy cycle에만 CLI live refs fallback 허용.

### DF27-03 — corrupted case-bank recovery requeue

재현:
1. case-bank/queue 생성 성공.
2. immutable case-bank의 `l1-review.json`을 손상.
3. queue packet만 제거하고 동일 case routing 재실행.

기존 결과:
- recovery return code 0.
- 손상된 case-bank를 재검증하지 않고 adversarial queue packet 재생성.

보완:
- recovery 전에 case-bank refs가 bundle 내부에 있는지 확인.
- evidence self-digest/case digest 재검증.
- deterministic policy file SHA-256 재검증.
- L1/L2 schema/self-digest 재검증.
- standards/spec/test SHA-256 재검증.
- ledger/anchor/case trail bundle 재검증.
- 하나라도 불일치하면 requeue하지 않고 fail-closed.

### DF27-04 — frozen-input 우선 수정의 route-only ref 호환 회귀

초기 DF27-02 수정은 `trusted-inputs/` 디렉터리가 존재하기만 하면 CLI standards/spec/test refs를 전부 무시했다.

기존 regression 결과:
- cycle에 해당 타입의 frozen input이 없고 route 단계에서만 ref를 추가하는 기존 경로가 비어 버림.
- 존재하지 않는 mutable standard ref를 fail-closed 하던 기존 테스트도 우회.

보완:
- 각 input 타입별로 **실제 frozen file이 존재할 때만** cycle snapshot을 우선.
- frozen file이 없는 타입은 기존 CLI ref 검증/freeze 동작 유지.
- standards provenance 비교는 cycle에 frozen standards가 실제 존재한 경우에만 적용.

## 추가 정합성 보완

- case-bank policy index marker를 v2.7로 갱신.
- dogfood 발견사항은 각각 executable regression으로 고정.
- meaningful hardening closeout에서 dogfood+fix를 기본 작업 규칙으로 추가.

## 검증 결과

최신 dogfood+fix code HEAD의 canonical push validation:
- package hygiene: PASS
- Git-blob manifest: **234 entries PASS**
- harness: **129 PASS / 71 isolated groups**
- vendored TextDiffChecker: **144 PASS / 1 GUI skip**
- DIFF-FALSE-EXACT: PASS
- `ALL VALIDATIONS PASS (FULL)`

## 최종 판정

세 가지 실제 runtime/downstream 결함과 한 가지 fix-induced compatibility regression을 같은 v2.7 candidate에서 보완했다. 최종 committed manifest와 clean-extracted package 검증은 closeout HEAD에서 다시 수행한다.
