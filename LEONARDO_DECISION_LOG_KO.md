# Leonardo Decision Log — v2.5

## D1. stable baseline이 candidate를 리뷰해야 한다
v2.5 개발 중 v2.4를 judge로 유지했다. candidate가 자기 변경을 자기 규칙으로 승인하는 self-confirming loop를 방지한다.

## D2. HEAD freshness만으로는 부족하다
PR 의미는 target/base ref 이동으로 바뀔 수 있다. 따라서 종료 시 base tip/merge-base까지 재확인한다.

## D3. attestation은 시간·대상에 묶여야 한다
HMAC만 유효한 오래된 sandbox statement는 재사용될 수 있다. case/base/head/freshness를 계약에 추가했다.

## D4. “sandbox=1” 같은 자기표시는 금지한다
실제 검증되지 않은 상태를 환경변수로 sandbox라고 표현하면 reviewer가 잘못된 신뢰 가정을 할 수 있다. verified/unverified를 분리했다.

## D5. backdata에는 실제 worker implementation을 구분할 수 있어야 한다
model/prompt digest만으로 로컬 worker wrapper 변경을 구분하기 어렵다. `worker_command_digest`를 추가해 calibration을 세분화한다.

## D6. reviewer environment도 정책 입력이다
allowlist 오설정으로 secret 환경변수가 worker에 들어가면 프롬프트 규칙으로 막을 수 없다. 이름 기반 fail-closed guard를 추가했다.

## D7. 검증 시스템도 dogfood 대상이다
thread → subprocess → multiprocessing 구조가 일부 POSIX 환경에서 불안정할 수 있었다. 테스트 격리 전략과 pipe handling 자체를 보완했다.

## D8. 새 audit event는 schema까지 함께 바뀌어야 한다
`RUNTIME_ATTESTED` 구현 직후 schema 누락을 신규 ENFORCED test가 잡았다. 기능·schema·ledger·validator를 하나의 변경 단위로 취급한다.

## D9. freshness만으로 replay를 막을 수 없다
짧은 유효시간의 HMAC attestation도 같은 case/base/head에서 여러 번 재사용될 수 있다. ENFORCED에서는 nonce를 repo 밖 launcher-owned replay cache에 원자적으로 claim하고, 두 번째 사용은 `ENFORCED_ATTESTATION_REPLAYED`로 차단한다. cache 삭제 권한까지 reviewer에게 주면 이 보장은 무효이므로 해당 디렉터리는 외부 trust boundary다.

## D10. 검증 커버리지 검사도 격리돼야 한다
모든 unittest 모듈을 validation parent에 import한 뒤 subprocess를 띄우는 것 자체가 multiprocessing 상태에 영향을 줄 수 있었다. test enumeration도 disposable subprocess에서 수행하고 실제 test group도 별도 OS process로 실행하며, group 종료 뒤 남은 descendant process group도 정리하도록 변경했다.


## D11. 검토 도구의 부산물이 검토 대상을 바꾸면 안 된다
v2.4 stable cycle 실행 자체가 candidate repo에 `__pycache__`를 생성해 종료 시 `WORKTREE_DIRTY_AFTER_REVIEW`를 유발하는 것을 dogfood에서 재현했다. v2.5 source tree는 Python bytecode/cache를 ignore하고, ignored cache가 worktree cleanliness 판정에 영향을 주지 않는 회귀 테스트를 유지한다.
