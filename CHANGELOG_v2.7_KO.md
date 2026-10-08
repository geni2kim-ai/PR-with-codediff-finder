# Changelog v2.7

## 목적

v2.6 hardening 후보를 다시 최신 HEAD 기준으로 검토하면서 발견된 **중단 복구(interruption/recovery), immutable snapshot, trusted-input/policy TOCTOU** 문제를 정식 릴리스 경계로 고정한다.

v2.7은 v2.6의 authority/ledger/sensor/runtime hardening을 유지하면서, 작업이 중간에 끊기거나 재개될 때 이전 상태가 현재 상태로 오인되지 않도록 복구 의미론을 강화한다.

## 주요 변경

- HUMAN attestation freshness를 **신규 승인 시점의 acceptance window**와 **과거 확정 증명의 검증**으로 분리.
- HUMAN recovery transaction 전체 digest + HUMAN authority-key HMAC 적용.
- HUMAN recovery 시 transaction ID 재계산 및 변조된 복구 상태 거부.
- ledger append에 authenticated recovery journal 도입.
- journal을 exact pre-append ledger bytes, hash chain, optional ledger HMAC authority에 바인딩.
- event fsync 후 anchor 교체 전 중단된 append를 재실행 시 idempotent하게 복구.
- 죽은 프로세스가 남긴 ledger lock PID를 즉시 회수.
- 동일 case_id 재사용 시 case-bank의 현재 case/binding/evidence와 immutable snapshot 일치 여부 확인.
- standards/spec/test를 reviewer 실행 전에 `trusted-inputs/`로 동결.
- policy/sensor policy를 cycle 시작 시 `effective-policy/`로 동결하고 생성·재계산·검증·reviewer provenance가 동일 snapshot을 사용.
- TextDiff evidence의 `config_sha256`을 실제 사용한 effective sensor policy에 바인딩.
- 저장소 기본 작업 지침에 **Latest-HEAD review rule** 추가.
- v2.7 policy/runtime/human/ledger integrity records의 현재 schema marker를 2.7로 갱신하고 v2.6 읽기 호환 유지.
- v2.7 release invariant 테스트 추가.
- committed MANIFEST 검증이 선행되는 PR/manual canonical validation 성공 뒤에만 동일 HEAD에서 `v2.7-source-package` ZIP artifact를 생성하도록 패키징 경로 고정.
- privacy-sensitive 원본을 재배포하지 않고 pre/post SHA-256 equality를 증명하는 digest-only mutation receipt 도구/스키마 추가 (`authority_effect=NONE`).
- mutation receipt 출력이 원본/spec/pre-snapshot을 덮어쓰는 경로를 fail-closed로 차단하고 receipt write를 atomic replace로 처리.
- receipt semantic validator를 추가하고 top-level/item 필드를 exact allowlist로 제한해 path/content 같은 추가 필드를 digest 재계산으로 숨기는 우회를 차단.
- `MANIFEST.sha256`을 `.git` 없는 추출 패키지에서 직접 검증하는 filesystem 모드 추가; missing/extra/hash mismatch와 unsafe POSIX 경로를 fail-closed.
- PR/manual package를 clean extraction한 뒤 manifest 검증과 canonical full validation을 다시 실행하도록 release gate 강화.
- exact HEAD + ZIP SHA-256 + manifest SHA-256 + entry count를 묶는 외부 source-package receipt 추가 (`authority_effect=NONE`).
- source-package receipt semantic validator를 schema와 동일한 package-name/type 계약으로 맞춤.
- tracked `.pytest_cache`, `__pycache__`, `*.pyc`, `*.pyo`를 manifest/package 생성 전에 거부하는 package hygiene gate 추가.
- `git archive --format=zip` clean-extract에서 일부 vendor text blob hash가 달라지는 문제를 검출하여, exact Git blob bytes를 직접 ZIP에 기록하는 package builder로 교체.
- CRLF/LF 혼합 blob의 archive/extract byte preservation 회귀 테스트 추가.
- ENFORCED runtime replay 회귀 테스트가 random L2 audit에 따라 간헐적으로 `WAITING_L2`가 되던 테스트 결합을 제거하고 L2 worker를 명시해 replay assertion을 안정화.

## 호환성

- 기존 reviewer/task/evidence/event JSON의 established `schema_version: "2.4"` wire contract는 그대로 유지한다.
- v2.6 ledger anchor/runtime attestation/human attestation/append-journal은 필요한 범위에서 읽기 호환한다.
- 새 v2.7에서 생성하는 policy, runtime attestation, human attestation, ledger anchor 및 recovery journal은 2.7 marker를 사용한다.

## 권한 상태

v2.7은 **HARDENED SHADOW CANDIDATE**이다. canonical validation PASS는 merge/HUMAN/ENFORCED 승격 권한을 대신하지 않는다.

- self-dogfood 후속: route 단계가 live policy를 다시 읽던 문제를 제거하고 cycle `effective-policy/` snapshot에 고정.
- self-dogfood 후속: review 후 standards/spec/test 원본 변조가 adversarial packet에 반영되던 TOCTOU를 제거하고 `trusted-inputs/`를 downstream authority로 사용.
- self-dogfood 후속: 손상된 immutable case-bank를 recovery가 재검증 없이 requeue하던 경로를 fail-closed.
- frozen-input 우선 처리에서 route-only refs 호환성이 깨진 회귀를 기존 테스트로 발견해 타입별 fallback으로 보완.

- finding triage 추가: `minor/nit`는 NOTE_ONLY로 기록하고 같은 closeout에서 자동 수정하지 않음.
- L1 `major` finding은 최소 L2 agent review를 요구하고 `blocker`는 기존 adversarial/higher escalation 유지.
- NOTE_ONLY finding은 `review-notes.json`에 `auto_fix=false`, `authority_effect=NONE`으로 저장.
- NOTE_ONLY만 있는 L1 FINDINGS와 L2 PASS는 material disagreement로 보지 않아 불필요한 adversarial loop를 차단.
- deterministic risk/protected-path floor 및 random audit는 finding triage보다 독립적으로 유지.

- finding triage authority hardening: config가 `major/blocker`를 NOTE_ONLY로 하향하거나 agent-review floor를 제거하지 못하도록 fail-closed.
- case trail에 `material_finding_count` / `note_only_finding_count`를 기록하고 downstream routing도 material disagreement만 승격.
- finding-triage regression 5건 추가; harness **134 PASS / 76 groups** 확인.
