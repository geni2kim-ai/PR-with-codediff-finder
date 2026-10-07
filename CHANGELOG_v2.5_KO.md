# v2.5 변경 기록

## 목적
v2.4를 안정 기준선으로 사용해 v2.5 수정 과정 자체를 SHADOW 리뷰하고, 그 과정에서 발견된 시간적 신뢰·실행 provenance·검증 러너 문제를 보완했다.

## 주요 변경

### 1. Base ref freshness
- 리뷰 시작 시뿐 아니라 종료 시에도 trusted base ref를 다시 resolve한다.
- base tip 또는 merge-base가 바뀌면 `BASE_REF_CHANGED_DURING_REVIEW`로 `STALE` 처리한다.
- HEAD만 고정되어 있어도 target branch가 움직인 PR을 이전 판정으로 통과시키지 않는다.

### 2. Runtime attestation hardening
- attestation을 `workspace + case_id + base_sha + head_sha`에 바인딩한다.
- `attestation_max_age_seconds`와 future-skew 제한을 정책에서 읽는다.
- ENFORCED에서 accepted attestation digest를 ledger의 `RUNTIME_ATTESTED` 이벤트로 남긴다.
- reviewer task에는 `runtime_attestation_digest`를 additive provenance로 전달한다.
- ENFORCED에서 nonce를 저장소 밖 launcher-owned replay cache에 원자적으로 claim하고 동일 attestation 재사용을 차단한다.

### 3. Sandbox 표기 정직성
- 무조건 설정되던 `MAESTRO_REVIEW_SANDBOX=1`을 제거했다.
- `MAESTRO_REVIEW_HARNESS=1`과 `MAESTRO_REVIEW_SANDBOX_VERIFIED=0|1`을 사용한다.
- 실제 attestation이 검증된 ENFORCED 경로만 sandbox verified로 표시한다.

### 4. Reviewer worker provenance
- worker argv와 실제 executable/script byte hash를 canonicalize하여 `worker_command_digest` 생성.
- task reviewer contract, stage result, case review trail에 연결.
- calibration에 `per_worker_command` 집계를 추가.

### 5. Environment boundary
- secret/token/password/credential/private-key/API-key/access-key/cookie/auth-header 계열 환경변수 이름을 allowlist에 넣으면 cycle이 `RUNTIME_CONFIG_INVALID`로 차단된다.
- `safe_env()`도 같은 이름을 방어적으로 전달하지 않는다.

### 6. Validation dogfood
- v2.4 방식 자체 검토 과정에서 candidate test runner의 fork/thread 조합 리스크를 확인했다.
- 테스트 stdout/stderr를 pipe 대신 임시 파일로 격리.
- multiprocessing-sensitive test는 별도 OS process group으로 실행.
- validation group이 신규 테스트를 누락하면 coverage guard가 실패한다.
- 각 isolated test group 종료 후 해당 process group의 남은 descendant를 정리해 다음 검증에 상태가 누적되지 않게 한다.
- dogfood reviewer가 생성한 Python bytecode가 candidate worktree를 dirty로 만들지 않도록 `__pycache__/`, `*.py[cod]`를 저장소에서 ignore한다.

## Dogfood 중 발견·수정된 통합 회귀
`RUNTIME_ATTESTED` 이벤트 기록 코드를 추가한 직후 case-event schema enum에 이벤트가 누락되어 정상 ENFORCED cycle이 `HARNESS_EXCEPTION`이 되는 문제가 신규 통합 테스트에서 발견됐다. v2.5에서는 schema를 보완하고 정상/만료 attestation 경로를 모두 회귀 테스트로 고정했다.


### 7. 최종 stable baseline 재검토
- packaged v2.4가 최종 HEAD `864ef63` 전체 diff를 다시 SHADOW review했다.
- 25 files / 1,006 changed lines, `HEURISTIC`, `trusted_for_gate=true`.
- governance/protected schema 변경으로 `HUMAN_REQUIRED`, gate `action_required`를 유지했다.
- candidate v2.5 자체 PASS와 stable authority 판정을 분리했다.
