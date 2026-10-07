# GitHub / Local PR Review Harness v2.3 변경 기록

## 목표
v2.2에서 구현한 TextDiff evidence sensor, semantic validator, RSI evaluator와 escalation policy를 **실제 로컬 L1/L2 리뷰 운영 루프**로 연결한다. 상위 모델을 직접 붙이지 않은 상태에서도 Adversarial packet을 만들어 사용자가 독립 모델로 크로스 검증하고 그 결과를 표준 개선 후보로 되돌릴 수 있게 한다.

## 주요 변경

### 1. L1/L2/Adversarial worker protocol
- `reviewer-task.schema.json` 추가.
- `reviewer-stage-result.schema.json` 추가.
- worker는 stdin으로 task JSON 하나를 받고 stdout으로 result JSON 하나만 반환한다.
- node/model/prompt/skill/policy/standards digest를 task가 고정하고, 결과가 이를 바꾸면 validator가 거부한다.
- shell 실행을 사용하지 않고 timeout/output size/environment allowlist를 적용한다.

### 2. L2 독립성 / Adversarial 정보 경계
- L1과 L2는 서로의 결과를 보지 않는다.
- L2 task에는 `lower_layer_result_refs=[]`가 강제된다.
- Adversarial은 이견을 adjudicate하기 위해서만 bounded L1/L2 refs를 받는다.
- L2/Adversarial은 fresh context가 요구된다.

### 3. Review cycle orchestration
`tools/run_review_cycle.py`가 다음을 수행한다.
- TextDiff evidence semantic 검증.
- protected path / sensor quality / large diff / weakening signal floor 계산.
- L1 호출 및 검증.
- 필요 시 L2 독립 호출.
- verdict 또는 blocker/major family 충돌 시 Adversarial 승격.
- Adversarial worker가 연결되지 않았으면 `adversarial-packet.json` 생성.
- HUMAN authority가 필요하면 `HUMAN_REQUIRED` 상태 유지.

### 4. SHA freshness 강화
- 리뷰 시작 전에 current HEAD를 확인한다.
- 모든 reviewer 호출이 끝난 뒤 HEAD를 다시 확인한다.
- 중간에 새 commit이 생기면 결과가 좋아도 전체 cycle을 `STALE / cancelled`로 전환한다.

### 5. Shadow / Enforced 분리
- 기본은 `SHADOW`.
- shadow 결과는 predicted gate일 뿐 실제 gate 권한이 없다.
- GitHub check preview는 shadow에서 무조건 `neutral`로 렌더링한다.
- `ENFORCED` 모드는 환경 secret stripping, network denial, workspace filesystem scoping, fresh L2/Adversarial model session attestation이 없으면 fail-closed한다.
- 현재 Python subprocess 자체는 OS 네트워크/파일시스템 sandbox를 제공한다고 주장하지 않는다.

### 6. Append-only Case Ledger
- `case-event.schema.json`, `case_ledger.py` 추가.
- 이벤트를 `seq + prev_hash + event_hash`로 연결한다.
- 과거 L1/L2 판정, escalation, outcome, incident, RSI, standard candidate의 이력을 덮어쓰지 않는다.

### 7. Outcome / post-merge feedback
- `ingest_outcome.py`로 author response, merge, post-merge 상태를 기록한다.
- `ingest_incident.py`는 incident/regression을 기록하고 `adversarial_reopen_required`를 붙인다.
- `route_case.py`는 post-merge incident를 critical adversarial 대상으로 승격한다.

### 8. 상위 모델 adjudication → standard candidate
- `adjudication.schema.json` 추가.
- `propose_standard_candidate.py` 추가.
- standard gap이 확인된 경우만 후보 생성 가능.
- 후보는 `PROPOSED`, `approval.required=[HUMAN,CODEOWNER]`, `approved=false`로 고정되어 자기 승인 불가.

### 9. Calibration
- `calibration_report.py` 추가.
- L1/L2/Adversarial/Human의 상위권한 판정 일치율, 단계별 reversal, PASS 후 post-merge incident를 집계한다.
- 상위 reviewer와의 일치율을 ground truth라고 간주하지 않는 경고를 출력한다.

### 10. Provenance digest 재현성
- policy/standards digest에서 로컬 절대 경로를 제거하고 content-set digest로 변경했다.
- 동일한 정책 바이트는 PC 경로가 달라도 동일 digest를 갖는다.

### 11. Effective policy provenance hardening
- `--routing-policy`로 커스텀 정책을 사용하는 경우 reviewer `policy_digest`가 실제 적용된 routing policy 바이트를 포함하도록 수정했다.
- 기본 package policy와 다른 실행 정책을 사용하면서도 동일 provenance로 보이던 공백을 제거했다.

### 12. BLOCKED / escalation 상태 정합성
- 최종 실행 reviewer가 `BLOCKED`를 반환하면 cycle도 `BLOCKED`로 고정하고 gate는 `action_required`가 된다.
- L1/L2/Adversarial 단계에서 새로 계산된 policy escalation 이유를 cycle에 누락하지 않고 누적한다.
- reviewer의 상향 요청은 `L1_REQUEST_*`, `L2_REQUEST_*`, `ADVERSARIAL_REQUEST_*`의 통제된 코드로 기록한다.

### 13. 검증 실행 경계 보강
- subprocess-heavy orchestration 테스트에는 명시적 timeout을 추가했다.
- 컨테이너 검증 환경에서 다수의 nested Git/Python subprocess를 단일 unittest 프로세스에 연속 누적할 때 descriptor 대기가 관찰되어, 공식 `run_validation.py --full`은 핵심 orchestration smoke와 전체 TextDiff regression을 묶고 나머지 orchestration cases는 독립 실행으로 검증했다.
- 이는 제품 review cycle의 판정 문제가 아니라 검증 실행 격리 문제이며, 실제 reviewer runtime은 별도 fresh-process 계약을 유지한다.

## 현재 상태
**Shadow deployment candidate.** 실제 로컬 L1/L2 worker command를 연결해 운영 데이터를 축적할 수 있다. 실제 merge-blocking은 reviewer isolation과 GitHub branch-protection 연결을 검증한 이후 별도 승인으로 승격해야 한다.
