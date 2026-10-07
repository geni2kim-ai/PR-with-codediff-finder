# v2.4 → v2.5 마이그레이션

## 호환성
JSON `schema_version`은 2.4를 유지한다. 다음 필드는 additive라 기존 snapshot을 계속 읽을 수 있다.
- reviewer task `runtime_enforcement.runtime_attestation_digest`
- reviewer contract/result/case trail `worker_command_digest`

새 v2.5 생성물에는 위 provenance를 기록한다.

## ENFORCED 사용자는 반드시 변경
기존 runtime attestation은 v2.5 ENFORCED에서 context/freshness 검증에 실패할 수 있다. 새 attestation은 현재 case id, merge-base SHA, HEAD SHA에 묶어 발급한다. 또한 `MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR`을 저장소 외부에 지정해야 하며, 승인된 nonce는 원자적으로 소비되어 재사용할 수 없다.

`policy/reviewer-routing.yml`의 다음 값을 운영 기준에 맞게 검토한다.
- `attestation_max_age_seconds`
- `attestation_max_future_skew_seconds`

## SHADOW 사용자
기본 사용법은 유지된다. 단, 리뷰 도중 base branch가 이동하면 이제 `STALE`이므로 evidence/review cycle을 새로 생성해야 한다.

## Backdata
v2.5 이후 case record는 가능한 경우 `worker_command_digest`를 남긴다. v2.4 이전 record에 해당 필드가 없어도 validator는 호환을 유지한다.
