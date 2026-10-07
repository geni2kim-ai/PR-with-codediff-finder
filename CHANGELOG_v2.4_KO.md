# Changelog v2.4

## P0 — 에스컬레이션/증거 우회 차단
- rename/copy `old_path` + new path 동시 분류.
- segment-aware protected-path matching 및 `./` 정규화 수정.
- merge-base → HEAD 비교로 전환.
- evidence Git metadata 재대조.
- bundled TextDiff adapter 재실행 후 `semantic_digest` 재현 검증.
- symlink/submodule/binary/coverage gap을 untrusted + 상위 review 신호로 승격.
- 시작/종료 worktree dirty 및 HEAD freshness 확인.

## P0 — 감사/무결성
- reviewer failure/timeout/invalid/unsafe/output-limit을 BLOCKED case + ledger event로 기록.
- reviewer stdout 실행 중 size cap 적용.
- concurrent ledger append lock.
- ledger anchor + ENFORCED HMAC anchor.
- snapshot↔event bundle validator 추가/강화.
- HUMAN_DECISION / RSI_EVALUATED / STANDARD_CANDIDATE_PROPOSED event writer 연결.

## 출력 안전
- `http/https/ftp`, `//host`, `www`, bare domain, markdown/HTML image, dangerous markdown link scheme, zero-width @mention, secret-like token 탐지.
- source_ref/failure_family/escalation reason까지 검사.
- reviewer self-report와 harness-computed safety flags 불일치 시 거부.

## Provenance / contract
- prompt/skill/standards ref missing 시 fail-closed.
- policy digest를 logical filename + bytes에 바인딩.
- reviewer default prompt를 `reviewer-worker-core.md`로 통일.
- task evidence/lower-layer refs 접근 가능성 및 digest 검증.
- certainty enum `judgment`로 통일.
- v2.4 active schemas/policies 정리.

## Queue / calibration
- 단일 queue policy 사용.
- governance/critical/disagreement/novel/low-confidence/RSI/random-audit 우선순위 통일.
- packet에 evidence/L1/L2 digest 포함.
- random audit와 policy escalation calibration strata 분리.
- invalid/unanchored case silent skip 제거.
- incident는 merged case에만 기록 가능.

## TextDiff
- `diff_texts_with_trace`와 기존 opcode API detail/cancel parity 복구.
- harness checker patch 재생성 및 원본 v1.4.6 적용 byte-match 검증.
- legacy encoding은 gate 관점 LOW confidence로 처리.
- DIFF-FALSE-EXACT quality classification 유지.

## Validation
- `run_validation.py`가 모든 harness unittest를 process-isolated 방식으로 실행.
- v2.4 전용 hardening 반례 추가: rename-out, evidence tamper, weakening tamper, merge-base, dirty tree, binary/symlink, output exfiltration, output cap, ledger concurrency/HMAC, config/provenance, trace parity 등.

## Closeout 추가 보완
- reviewer stderr도 별도 실행 중 cap(`max_stderr_bytes`)으로 제한.
- runtime attestation의 필수 boolean 항목을 `reviewer-routing.yml`의 `required_attestation_fields`에서 실제로 읽어 검증.
- subagent `default_max_children <= hard_max_children` 설정 불변조건 검사.
- 보조 `reviewer-core.md`의 출력 계약을 v2.4 `reviewer-stage-result.schema.json`으로 정합화.
- TextDiff trace parity random corpus를 1,500 case로 확대.
- 공식 validation runner를 전체 58개 harness test의 병렬 process-isolated 실행으로 고정.
- 최종 full validation: Harness 58 PASS + TextDiff 144 PASS(1 GUI skip) + schema/semantic/ledger/fixture PASS.
