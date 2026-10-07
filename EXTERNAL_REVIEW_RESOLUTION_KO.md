# v2.3 외부 재검토 → v2.4 처리표

## A. 높음

| # | 지적 | v2.4 처리 | 상태 |
|---|---|---|---|
| 1 | rename으로 보호 경로 이탈 | rename/copy의 `old_path`와 new path를 모두 분류. `auth/login.py → lib/login.py` 회귀 테스트 추가 | 해결 |
| 2 | evidence digest 재계산으로 진위 우회 | trusted base/HEAD/merge-base와 Git metadata 대조 + bundled adapter 재실행 + `semantic_digest` 재현 일치 필수 | 해결 |
| 3 | 중첩 보호 경로 매칭 오류 | `lstrip('./')` 제거, segment-aware suffix glob 구현. nested auth/infra/.github workflow 반례 추가 | 해결 |
| 4 | symlink/binary/submodule silent L1 | non-text/coverage gap은 sensor untrusted. `nontext_sensitive_change`를 Adversarial signal로 연결 | 해결 |

## B. 중간

| # | 지적 | v2.4 처리 | 상태 |
|---|---|---|---|
| 5 | 2-dot diff | base tip은 provenance로 보존하되 실제 비교는 `merge-base(base, head) → head` | 해결 |
| 6 | dirty worktree 미검출 | 리뷰 시작/종료에 tracked+untracked 검사. HEAD도 종료 시 재확인 | 해결 |
| 7 | reviewer 실패 audit 소실 | timeout/process exit/invalid JSON/unsafe/output-limit을 `REVIEW_FAILED`, `review-failure.json`, `BLOCKED` cycle로 기록. `--retry`는 immutable attempt 생성 | 해결 |
| 8 | ledger truncation/re-hash/concurrency | append lock + 별도 anchor. ENFORCED는 외부 HMAC key 필수. snapshot↔event 검증 추가. SHADOW 무키 anchor는 보안 권한이 아닌 corruption detector로 명시 | 해결/경계 명시 |
| 9 | output safety 우회 | URL/domain/protocol-relative/www/ftp/image/dangerous scheme/mention/zero-width mention/secret scan 확대. `source_ref`, `failure_family`, escalation reason 포함. 하네스 계산값과 self-report 일치 필수 | 해결 |
| 10 | 기본 prompt가 v2.2 계약 | routing default를 `reviewer-worker-core.md`로 통일. 보조 reviewer-core도 `reviewer-stage-result.schema.json`으로 정합화 | 해결 |
| 11 | 설정 파일이 코드에 미연결 | escalation/sensor/random-audit/review/subagent/calibration/encoding/runtime-attestation 필드를 실제 로직에서 읽음. 잘못된 subagent limit은 fail-closed | 해결 |
| 12 | validation runner가 15개 전부 안 돌림 | 모든 harness unittest method를 process-isolated로 실행. 현재 58/58 PASS | 해결 |
| 13 | max_output_bytes 사후 검사 | stdout을 임시파일로 stream하며 실행 중 size 감시. stderr도 별도 cap 추가 | 해결 |
| 14 | queue 우선순위/packet 누락 | 단일 `queue_policy.py` 사용. governance→critical→disagreement→novel→low-confidence→RSI→random-audit. packet에 evidence/L1/L2 digest 포함 | 해결 |
| 15 | calibration 선택 편향/silent skip | random-audit labels를 case에 보존, strata 분리. invalid/unanchored JSON/ledger는 결과에 명시 | 해결 |
| 16 | weakening signal 정확도 | `__tests__`, `.test/.spec`, `*_test.go`, `test_`를 test-path로 인식. non-test `stream.skip`는 제외. rename-only에서 추가 line이 없으면 skip signal 없음 | 해결 |
| 17 | provenance digest 허점 | logical filename + content hash 쌍을 canonical digest. missing prompt/skill/standards ref fail-closed | 해결 |

## C. 낮음 처리

- task `evidence_ref`는 절대 경로로 제공되고 `evidence_digest`/`semantic_digest`에 바인딩됨.
- TextDiff trace fork parity를 1,500 random case로 회귀 고정.
- cp949/shift_jis/cp1252/latin-1 fallback은 gate 관점 LOW confidence.
- random audit는 case-id deterministic hashing을 사용하지 않고 CSPRNG; ENFORCED는 외부 audit seed 필수.
- ENFORCED runtime attestation은 외부 HMAC 검증을 요구. 단, 실제 OS sandbox 자체는 여전히 NOT_RUN.
- TextDiff checker/package/vendor+harness requirements hash를 `sensor-policy.yml` pin과 비교.
- `certainty` 표기를 `confirmed | likely | judgment`로 통일.
- `ingest_incident.py`는 `merged=true`가 아니면 거부.
- active queue 경로는 `adversarial_queue/`로 통일하고 과거 문서는 `history/`에 보관.
- 하네스/runtime dependency 버전과 requirements digest를 evidence tool metadata에 기록.

## 남아 있는 외부 전제

다음은 v2.4 코드 하드닝과 별개로 실제 배포 환경에서 검증해야 한다.

1. OS 수준 network deny / workspace-only filesystem sandbox.
2. 실제 L1/L2/Adversarial model worker 및 fresh-session attestation issuer.
3. GitHub Check Run API + required check + branch protection/ruleset E2E.
4. Windows GUI/PyInstaller E2E.
5. 실제 post-merge incident source connector.

따라서 현재 권장 모드는 `SHADOW`이며, 위 전제를 통과하기 전 `ENFORCED` 승격은 금지한다.
