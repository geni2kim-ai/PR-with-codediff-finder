# Leonardo v2.7 추가 시뮬레이션 및 보완 결과

## 기준

- 시작 HEAD: `c0e5ab7897c4cfffe03d3a100041c7f04ca37152`
- 목적: v2.7의 단기 anti-loop/등급 정책이 Leonardo 장기 backdata와 결합될 때 잘못된 학습 또는 불필요한 상위검토를 만드는지 확인.
- 원칙: high-impact finding은 같은 candidate에서 수정. low/medium optimization은 NOTE로 남겨 새 수정 루프를 만들지 않는다.

## 시뮬레이션 결과

### LEO27-01 — NOTE_ONLY calibration false disagreement

**중요도: HIGH / FIXED**

L1이 오타 하나 때문에 raw `FINDINGS`, L2가 `PASS`인 경우 기존 calibration은 reversal로 집계할 수 있었다.

영향:
- L1 precision/agreement를 실제보다 낮게 평가;
- 향후 L1을 더 공격적으로 만들거나 L2 비율을 불필요하게 높일 위험.

수정:
- material finding count를 기준으로 PASS/FINDINGS state를 재해석.
- NOTE_ONLY-only review는 calibration상 material PASS.

### LEO27-02 — HUMAN verdict vocabulary mismatch

**중요도: HIGH / FIXED**

HUMAN은 `CONFIRMED/REJECTED`, machine reviewer는 `PASS/FINDINGS/BLOCKED`를 사용한다. 이를 raw string으로 최고 authority와 비교하면 machine agreement가 구조적으로 왜곡된다.

수정:
- L1/L2/ADVERSARIAL accuracy는 최고 machine review의 material state와 비교.
- HUMAN은 parent review confirmation/rejection 통계로 별도 기록.

### LEO27-03 — broad family false repeated-finding

**중요도: HIGH / FIXED**

기존 material repeat key가 failure family 하나를 우선해, `CORRECTNESS` 계열의 서로 다른 파일 결함이 연속되면 같은 문제 반복으로 오인해 HUMAN_REQUIRED로 너무 빨리 갈 수 있었다.

수정:
- repeat identity를 failure family + axis + path로 구성.
- wording/line movement에는 비교적 안정적이면서 다른 파일의 별도 결함은 분리.

### LEO27-04 — NOTE backlog 장기 학습

**중요도: MEDIUM-HIGH / FIXED within bounded scope**

anti-loop 정책은 NOTE를 자동 수정하지 않기 때문에 반복 NOTE를 standard evolution 후보로 볼 수 있어야 한다.

수정:
- case record에 note-only finding key/family를 보존.
- case-frequency로 deduplicate.
- 기본 3 case 반복부터 calibration report에 recurring-note proposal signal 출력.
- 자동 source fix/standard update는 금지.

### LEO27-05 — remediation 과거 attempt 전체 provenance 보존

**중요도: MEDIUM / NOTE**

최종 case record에는 campaign summary가 포함되지만 이전 attempt의 모든 model/prompt/worker provenance trail을 하나로 재봉인하지는 않는다.

영향:
- campaign attempt 수/반복/시간 지표는 계산 가능.
- 이전 attempt까지 포함한 완전한 per-model precision 분석에는 정보가 부족할 수 있음.

판정:
- 현재 release correctness/authority 결함이 아니라 Leonardo analytics 완전성 개선.
- 이번 candidate에서 구조를 더 확대하면 새 schema/packet/case-bank 변경 범위가 커지므로 NOTE로 남김.

## 검증

새 regression:
- NOTE_ONLY material-state calibration
- HUMAN confirmation vocabulary separation
- same-family/different-path repeat identity
- recurring NOTE case-frequency aggregation

code-bearing 결과:
- harness **145 PASS / 87 groups**
- TextDiffChecker **144 PASS / 1 GUI skip**
- DIFF-FALSE-EXACT PASS
- canonical full validation PASS

## 결론

v2.7의 즉시 리뷰 루프뿐 아니라 Leonardo의 장기 학습 루프도 **사소한 NOTE 때문에 reviewer가 점점 공격적으로 변하는 방향**을 피하도록 보완했다.

반복 NOTE는 수정 루프가 아니라 standard/check proposal 신호가 되고, HUMAN verdict는 machine accuracy와 분리되며, 서로 다른 동일-family 결함은 자동 반복 실패로 잘못 합쳐지지 않는다.

## 추가 Leonardo 시뮬레이션 — authority-path / campaign-budget 교차 검증

추가 시뮬레이션에서 자동 반복 시간을 불필요하게 늘리거나 HUMAN을 조기 요구할 수 있는 두 가지 경계를 확인했다.

### 1. 상위 리뷰가 기각한 하위 material finding의 budget 잔존

기존 구현은 한 attempt 안의 L1/L2/Adversarial 모든 material finding key를 합집합하여 review budget에 넣었다.

반례:
- L1: major `CORRECTNESS` finding
- L2: PASS
- Adversarial: PASS

이 경우 최종 machine authority는 finding을 기각했지만, L1 key가 campaign material key에 남아 이후 같은 key가 다시 관찰되면 `SAME_MATERIAL_FINDING_REPEAT`로 잘못 HUMAN을 요구할 수 있었다.

보완:
- campaign material key는 **최고 완료 machine authority 단계에서 살아남은 material finding**만 사용한다.
- L2/Adversarial이 하위 finding을 기각하면 해당 key는 remediation/repeat budget에서 제거한다.
- 하위 리뷰 기록 자체는 review trail/calibration 근거로 계속 보존한다.

### 2. WAITING_L2 / ADVERSARIAL_REQUIRED 재개가 remediation attempt를 소비

기존 구현은 immutable output directory 수를 그대로 `attempt_index`로 사용했다.

반례:
1. L1 major → `WAITING_L2`
2. 동일 HEAD에서 L2 재개 → `ADVERSARIAL_REQUIRED`
3. 동일 HEAD에서 Adversarial 재개 → 완료

정책상 위 흐름은 한 번의 remediation attempt에서 미완성 authority path를 완성하는 과정인데, 기존에는 attempt 1/2/3으로 세어 세 번째 단계에서 자동 remediation 한도에 닿을 수 있었다.

보완:
- 동일 HEAD의 `WAITING_L2` / `ADVERSARIAL_REQUIRED` 재개는 같은 logical `attempt_index`를 유지한다.
- 새 HEAD를 만드는 실제 material remediation 때만 logical attempt가 증가한다.
- output directory는 계속 immutable하게 새로 만들되, directory sequence와 remediation budget sequence를 분리한다.
- HUMAN_REQUIRED 이후 자동 재개 금지, NOTE_ONLY closeout 재시작 금지, material remediation의 HEAD 변경 요구는 그대로 유지한다.

추가 회귀:
- higher-authority clearance가 lower-stage material을 budget에서 제거하는지 확인
- WAITING_L2 재개가 `attempt_index=1`을 유지하는지 확인
- WAITING_L2 → ADVERSARIAL_REQUIRED → COMPLETE 동일 HEAD 흐름이 logical attempt 1개만 사용하는지 확인

이 보완은 권위 단계를 낮추지 않는다. 목적은 **검토 단계 완성**과 **실제 소스 보완 반복**을 분리하여, 불필요한 반복 시간과 false HUMAN escalation을 줄이는 것이다.

## 추가 Leonardo 시뮬레이션 — historical campaign state / retry integrity

앞선 authority-path 보완을 다시 역방향으로 시뮬레이션한 결과 두 가지 경계 문제가 추가로 확인되었다.

### 3. 상위 authority에서 해소된 finding이 history 재로딩 시 다시 material로 부활

직전 보완에서 현재 attempt의 budget 계산은 최고 완료 machine authority 단계만 보도록 수정했지만, 다음 실행에서 과거 attempt를 읽는 `campaign_history()`는 여전히 모든 review trail의 material count/key를 합산하고 있었다.

반례:
1. L1 = major
2. L2 = PASS
3. Adversarial = PASS
4. 현재 attempt는 `NO_MATERIAL_FINDINGS`로 정상 종료
5. 이후 무관한 새 HEAD가 생긴 뒤 `--retry`

기존 history 재로딩에서는 L1 major가 다시 material로 계산되어 닫힌 campaign을 remediation 가능 상태처럼 취급할 수 있었다.

보완:
- 과거 이력의 material 상태도 최고 완료 machine authority 단계 기준으로 계산한다.
- 신규 v2.7 close event에는 `current_material_finding_keys`를 ledger에 함께 기록한다.
- 이후 retry에서는 ledger에 앵커된 authoritative key가 있으면 그것을 우선 사용한다.
- 따라서 상위 review에서 해소된 lower-stage finding은 현재 attempt뿐 아니라 이후 재실행에서도 다시 살아나지 않는다.

### 4. mutable history metadata가 retry/HUMAN 경계를 바꿀 수 있는 문제

기존 `campaign_history()`는 `case-record.json`의 campaign metadata와 `review-cycle.json`의 state를 직접 읽었다. 두 파일의 해당 필드는 retry 판단에 사용되면서도 그 값 자체를 campaign ledger의 close event에서 다시 확인하지 않았다.

보완:
- 과거 case bundle과 ledger/anchor를 먼저 검증하고, 불일치 시 retry를 fail-closed 한다.
- historical state는 ledger의 `CYCLE_CLOSED.payload.state`에서 읽는다.
- historical HEAD는 ledger의 `CASE_OPENED.payload.head_sha`에서 읽는다.
- logical attempt index는 validated history의 HEAD/state 전이를 통해 독립적으로 재계산한다.
- 신규 `CYCLE_CLOSED`에는 `attempt_index`, `current_material_finding_keys`, `review_budget_digest`를 함께 기록한다.
- case metadata의 `attempt_index` 또는 review-cycle state만 바꾸어서는 retry budget을 변경할 수 없다.
- ledger event를 직접 변조하면 hash/anchor 검증에서 history 자체가 거부된다.

추가 회귀:
- higher-authority clearance 후 무관한 새 HEAD가 생겨도 closed campaign이 재개되지 않음
- mutable review-cycle state 변조가 anchored state를 덮어쓰지 못함
- CYCLE_CLOSED ledger state 변조는 history invalid로 fail-closed
- case-record campaign attempt_index 변조가 logical attempt budget을 바꾸지 못함

SHADOW의 unkeyed anchor는 self-consistency 보장 범위이고 외부 공격자에 대한 독립 authority를 의미하지 않는다. ENFORCED에서는 기존 HMAC key 요구를 그대로 사용한다.

### 5. WAITING_L1이 실제 reviewer 실행 없이 remediation budget을 소모

추가 시간축 시뮬레이션:
1. L1 worker 미지정 → `WAITING_L1`
2. 동일 HEAD 재개, worker 아직 미지정 → 다시 `WAITING_L1`
3. 이후 L1 worker가 준비되어 정상 리뷰 시작

기존에는 각 resume가 새 logical attempt로 계산되어 reviewer가 한 번도 실행되지 않았는데도 자동 remediation 한도에 접근할 수 있었다.

보완:
- 동일 HEAD의 `WAITING_L1`도 `WAITING_L2`, `ADVERSARIAL_REQUIRED`와 동일하게 unfinished authority-path resume로 취급한다.
- output directory는 immutable하게 계속 분리하지만 `attempt_index`는 증가하지 않는다.
- 여러 번 WAITING_L1 상태를 거친 뒤 처음 L1 reviewer가 실행되어도 logical attempt는 1을 유지한다.
- HEAD가 바뀌거나 완료된 material remediation을 다시 검토하는 경우에는 기존 규칙대로 새 attempt가 된다.

회귀 테스트에서 WAITING_L1을 두 번 연속 재개한 뒤 L1 PASS로 완료하는 전체 흐름이 `attempt_index=1`을 유지하는지 고정했다.

### 6. reviewer 완료 후 closeout 이전 중단 시 동일 agent 작업 재실행

중단 시나리오를 `CYCLE_CLOSED` 이전까지 세분화하여 시뮬레이션했다.

반례:
1. L1 reviewer가 실제 실행되어 결과와 `REVIEW_COMPLETED` ledger event까지 기록
2. `case-record.json` / `CYCLE_CLOSED` 작성 전에 프로세스 중단
3. 동일 HEAD에서 `--retry`

기존 `campaign_history()`는 `case-record.json`이 없는 attempt directory를 아예 이력에서 제외했다. 따라서 이미 비용을 지불한 L1 reviewer가 다음 실행에서 다시 호출될 수 있었다. 반복 budget 숫자는 증가하지 않더라도 실제 agent 시간/토큰은 중복 소비되는 경로였다.

보완:
- case record가 없어도 ledger/anchor가 존재하는 attempt를 검사한다.
- ledger hash chain과 anchor가 유효하고 `CASE_OPENED`가 존재하며 `CYCLE_CLOSED`가 없으면 내부적으로 `INTERRUPTED_EMPTY` 또는 `INTERRUPTED_REVIEW` 상태로 복구 대상으로 분류한다.
- 동일 HEAD의 interrupted attempt는 동일 logical attempt를 유지한다.
- 이전 task/result pair가 현재 task와 완전히 호환되면 기존 SHADOW reuse 검증을 그대로 적용하여 완료된 L1/L2 결과를 재사용한다.
- `CYCLE_CLOSED`는 있는데 case record가 사라진 비정상 상태는 정상 중단으로 간주하지 않고 fail-closed 한다.
- reviewer 완료 후 중단된 상태에서 HEAD가 바뀌면 그 reviewer-bearing attempt는 이미 실제 검토 비용을 사용한 attempt로 계산한다. crash 후 HEAD 변경을 반복하여 자동 attempt 한도를 우회할 수 없다.

추가 회귀:
- L1 완료 직후 closeout 전 중단 → 동일 HEAD retry에서 L1 worker가 두 번째로 호출되지 않음
- 위 경로에서 `reused_agent_stages=1`, logical `attempt_index=1` 유지
- reviewer 완료 중단 후 HEAD 변경 → 다음 실행은 logical attempt 2
- closed ledger인데 case record가 없는 경우 history invalid로 fail-closed

이 보완은 interruption을 무조건 무료 retry로 취급하지 않는다. **실제 reviewer가 실행되지 않은 중단은 재개**, **이미 reviewer 비용을 쓴 중단은 그 작업을 재사용하거나, HEAD가 바뀌면 사용한 attempt로 계산**하는 방식으로 시간 절약과 budget 우회 방지를 동시에 맞춘다.

### 7. resume 재실행으로 hard worker-time ceiling을 초과할 수 있는 문제

문서에는 기본값 기준 `3 attempts × 3 reviewer levels × 180초 = 1,620초`가 hard worker-time ceiling으로 정의되어 있었지만, 기존 구현은 그 값을 `review-budget.json`에 계산하여 기록할 뿐 campaign 전체 reviewer 호출 횟수에는 직접 강제하지 않았다.

반례:
- 동일 HEAD에서 unfinished authority path를 여러 번 resume
- 이전 task/result가 정책/입력 변경 등으로 reuse 불가
- 같은 logical attempt 안에서 reviewer가 반복 재실행
- `attempt_index`는 증가하지 않으므로 3-attempt 제한을 건드리지 않으면서 실제 worker 시간은 1,620초를 넘어갈 수 있음

보완:
- 각 validated campaign directory의 ledger에서 실제 worker invocation 수를 재구성한다.
- `REVIEW_COMPLETED` 중 `reused_from_previous_attempt=false`인 실행과 `REVIEW_FAILED`를 실제 invocation으로 센다.
- reuse된 기존 결과는 worker time을 다시 소비하지 않으므로 한도에서 제외한다.
- 기본 campaign 전체 invocation ceiling은 기존 정책식과 동일하게 `max_automated_attempts × 3`으로 강제한다.
- 이미 ceiling에 도달한 상태에서는 새 retry를 시작하지 않고 HUMAN/owner 결정을 요구한다.
- 한 실행을 시작할 때는 한도 미만이었더라도 L2 실행으로 9번째를 채운 뒤 Adversarial이 10번째가 되는 경우, Adversarial worker를 호출하기 전에 `REVIEW_CAMPAIGN_WORKER_BUDGET_EXHAUSTED`로 차단한다.

추가 회귀:
- 동일 logical attempt의 interrupted L1 흔적 9개 → 다음 retry가 reviewer를 다시 호출하지 않고 즉시 budget exhaustion
- 누적 8회 상태에서 L1 reuse + L2 실행으로 9회 도달 → 10번째 Adversarial 호출 직전 BLOCKED
- 여러 interrupted/resumed directory가 모두 logical attempt 1이어도 실제 reviewer invocation은 별도로 누적

이로써 logical remediation attempt 제한과 실제 agent 실행시간 제한이 분리된다. **resume은 attempt를 불필요하게 소비하지 않지만, resume 자체가 무제한 agent 재실행 통로가 되지도 않는다.**

### 8. reviewer 실행 실패가 source remediation attempt를 소모하는 문제

worker-time ceiling을 강제한 뒤 failure path를 다시 시뮬레이션했다.

반례:
1. L1 major 완료
2. L2 reviewer가 timeout / process exit / invalid JSON 등 실행 오류로 실패
3. 소스 HEAD는 그대로
4. 동일 HEAD에서 retry

기존에는 해당 cycle이 `BLOCKED`로 닫히므로 다음 retry가 새 remediation attempt로 계산되었고, resume 대상에서도 제외되어 이미 성공한 L1까지 다시 실행될 수 있었다. source remediation은 전혀 일어나지 않았는데 source-remediation budget과 worker 비용을 동시에 소모하는 구조였다.

보완:
- reviewer execution failure 중 `REVIEW_TIMEOUT`, `REVIEW_OUTPUT_LIMIT`, `REVIEW_STDERR_LIMIT`, `REVIEW_PROCESS_EXIT`, `REVIEW_INVALID_JSON`, `REVIEW_UNSAFE_OUTPUT`, `REVIEW_INVALID_RESULT`은 동일 HEAD에서 resumable execution failure로 분류한다.
- 이 경우 logical `attempt_index`는 증가하지 않는다.
- 이전 L1/L2 task/result가 현재 입력과 호환되면 기존 SHADOW reuse 검증을 거쳐 재사용한다.
- 실패했던 stage만 다시 실행한다.
- 실제 실패 호출은 `REVIEW_FAILED` ledger event로 worker invocation ceiling에 계속 포함된다.
- `INVALID_TASK`, campaign worker-budget exhaustion, 일반 harness/policy block은 자동 resumable failure로 취급하지 않는다.

회귀:
- L1 major 성공 + L2 process-exit 실패 → state BLOCKED
- history는 `failure_kind=REVIEW_PROCESS_EXIT`, resumable=true, logical attempt 1로 재구성
- 동일 HEAD retry에서 L1 worker 재호출 없이 L1 결과 재사용
- L2만 다시 실행하고 최종 budget의 `attempt_index=1` 유지

이제 **source를 고쳐 다시 검토하는 반복**과 **reviewer 실행 자체의 일시 실패를 재시도하는 반복**이 서로 다른 budget으로 관리된다. 전자는 3 remediation attempts, 후자는 campaign-wide worker invocation ceiling으로 각각 제한된다.

### 9. 강화된 history 검증이 다른 case의 정상 retry를 막는 호환성 회귀

campaign history를 ledger/anchor 기반으로 강화한 뒤 canonical regression에서 기존 v2.4 테스트가 실제 실패했다.

재현:
1. 동일 output root에 case A의 BLOCKED cycle 존재
2. 같은 root에 case B를 `--retry`로 새 immutable attempt 생성
3. history scanner가 case A ledger를 case B의 ID로 검증
4. case ID mismatch로 case B 시작 자체가 차단

보안 강화 과정에서 생긴 실제 회귀였으며, 기존 동작상 output root가 반드시 단일 case 전용이라는 보장은 없었다.

보완:
- 각 ledger는 먼저 자기 event들의 case ID가 하나로 일관되는지 확인한다.
- ledger hash chain과 anchor는 그 ledger 자신의 case ID 기준으로 검증한다.
- 검증이 끝난 뒤 active `case_id`와 다른 정상 case ledger는 현재 campaign history에서 제외한다.
- ledger 내부에 case ID가 섞였거나 누락된 경우는 계속 fail-closed 한다.
- active case의 ledger/case-record 불일치는 계속 오류다.

이 수정으로 **shared immutable output root의 case isolation**을 유지하면서, 다른 case를 현재 campaign 이력으로 잘못 해석하는 회귀를 제거했다. 기존 `test_reviewer_failure_is_audited_and_retry_gets_new_attempt`가 이 경계를 다시 검증한다.

### 10. reviewer가 시작된 뒤 완료/실패 event 이전에 harness가 죽으면 worker ceiling을 우회

worker invocation ceiling을 ledger의 `REVIEW_COMPLETED`와 `REVIEW_FAILED`만으로 계산하면 다음 경계가 남는다.

반례:
1. worker process가 실제 시작
2. 모델이 토큰/시간을 소비
3. harness 또는 host가 worker 종료 결과를 ledger에 쓰기 전에 중단
4. 다음 실행에서 completed/failed event가 없으므로 이전 호출을 0회로 계산

이 중단을 반복하면 logical attempt는 증가하지 않으면서 실제 worker 비용만 계속 발생하여 9회 hard ceiling을 우회할 수 있었다.

보완:
- worker process를 호출하기 **직전** ledger에 `REVIEW_STARTED`를 기록한다.
- event에는 level, task ID/digest, logical attempt index, campaign worker invocation index를 포함한다.
- `REVIEW_STARTED`가 존재하는 신규 ledger는 실제 invocation 수를 start event 개수로 계산한다.
- 기존 v2.7 ledger는 backward compatibility를 위해 `REVIEW_COMPLETED(non-reuse) + REVIEW_FAILED` 방식으로 계산한다.
- process 생성 자체가 실패해도 이미 start attempt를 사용한 것으로 보수적으로 계산한다.
- review budget에 `campaign_worker_invocation_ceiling`과 `campaign_worker_invocations_used`를 명시하여 실제 사용량을 확인할 수 있게 했다.

회귀:
- L1 `REVIEW_STARTED` 직후 crash 상태를 수동 재현 → worker invocation 1로 복구
- started-only crash를 9회 누적 → 10번째 reviewer 시작 전 차단
- same-HEAD 재개에서는 remediation attempt 1 유지

### 11. 완료 event 없이 남은 result 파일을 SHADOW reuse가 신뢰할 수 있는 문제

`record_stage()`는 review result 파일을 먼저 저장하고 이후 `REVIEW_COMPLETED` ledger event를 쓴다. 따라서 result 파일 저장 직후 중단될 수 있다.

기존 `reusable_stage_result()`는 task/result schema와 provenance가 맞으면 파일을 재사용했기 때문에, ledger상 완료되지 않은 partial result도 reuse 후보가 될 수 있었다.

보완:
- result reuse에 기존 task/result/provenance 검증을 모두 유지한다.
- 추가로 previous ledger/anchor가 유효해야 한다.
- 같은 level과 정확한 `result_digest`를 가진 `REVIEW_COMPLETED` event가 존재해야만 reuse한다.
- started-only 상태에서 result 파일이 남아 있어도 완료 증거가 없으면 reviewer를 다시 실행한다.
- 이전 started invocation은 worker ceiling에는 이미 1회로 남으므로 중복 실행이 무한히 무료가 되지 않는다.

### 12. worker executable 시작 실패가 일반 HARNESS_EXCEPTION으로 분류되는 문제

존재하지 않는 executable, OS process-create 오류 등 `subprocess.Popen()` 자체의 실패는 기존 `ReviewerExecutionError` 경로를 타지 않아 일반 harness exception으로 처리될 수 있었다.

보완:
- process-create `OSError`를 `PROCESS_START` reviewer execution failure로 변환한다.
- ledger에는 `REVIEW_STARTED` + `REVIEW_FAILED(kind=PROCESS_START)`가 남는다.
- 동일 HEAD에서는 execution retry로 취급하여 logical remediation attempt를 증가시키지 않는다.
- 실제 호출 시도는 worker invocation ceiling 1회를 소비한다.

결과적으로 reviewer 비용 관리는 이제 **시작 시점(start), 결과 확정(completed/failed), stage 재사용(completion proof)** 세 경계가 ledger로 연결된다.

### 13. SHADOW + ledger HMAC에서 정상 resume reuse가 비활성화되는 문제

선택적으로 `MAESTRO_LEDGER_HMAC_KEY`를 사용하는 SHADOW 경로를 시뮬레이션했다.

기존에는 campaign history는 HMAC key로 ledger/anchor를 정상 검증했지만, `reusable_stage_result()`가 같은 anchor를 다시 확인할 때 key를 전달하지 않았다. HMAC이 존재하는 정상 anchor도 "key unavailable"로 판단되어 lower-stage reuse가 실패하고 reviewer를 다시 실행할 수 있었다.

보완:
- stage reuse 검증에도 동일 ledger HMAC key를 전달한다.
- HMAC이 설정된 SHADOW에서 WAITING_L2 resume 시 검증된 L1 결과를 정상 재사용한다.
- HMAC 검증 실패 시에는 기존처럼 reuse하지 않는다.

회귀 테스트에서 HMAC anchor를 사용한 동일 HEAD resume가 L1 worker를 두 번째로 호출하지 않고 `reused_agent_stages=1`, `attempt_index=1`을 유지하는지 고정했다.

### 14. 동일 campaign 동시 retry가 worker ceiling을 병렬로 초과할 수 있는 문제

campaign-wide worker ceiling을 강화한 뒤 동시 실행을 시뮬레이션했다.

반례:
1. 동일 output root에서 두 프로세스가 거의 동시에 `--retry`
2. 두 프로세스 모두 같은 historical worker count를 읽음
3. 각자 "아직 ceiling 미만"이라고 판단
4. 서로 다른 reviewer를 동시에 시작
5. 개별 ledger는 정상이어도 campaign 전체 실제 호출 수가 ceiling을 초과할 수 있음

보완:
- 동일 case ID에는 campaign 전체 동안 유지되는 single-writer lock을 적용한다.
- 동일 case의 병렬 retry는 reviewer를 하나도 시작하지 않고 즉시 거부한다.
- 서로 다른 case ID는 같은 output root를 공유해도 병렬 실행할 수 있다.
- 전역 attempt 번호 충돌만 막기 위해 output directory 할당 구간에는 별도의 짧은 root allocation lock을 사용한다.
- 최초 root allocation 시 reservation marker를 남겨 두 프로세스가 동시에 root 자체를 첫 attempt로 선택하지 못하게 한다.
- dead owner PID의 lock은 기존 ledger lock 복구 규칙과 동일하게 회수된다.

### 15. attempt 디렉터리 복제/삭제/재배열로 campaign history가 왜곡되는 문제

각 attempt 내부 ledger/anchor가 유효해도 campaign history는 디렉터리 집합 자체를 신뢰하고 있었다.

반례 A — 복제:
- 완료/중단 attempt 디렉터리를 그대로 복사하여 `attempt-000N`으로 추가
- 같은 worker invocation이 여러 번 계산되어 false worker exhaustion/HUMAN escalation 가능

반례 B — 중간 삭제:
- `attempt-0001`, `attempt-0002`, `attempt-0003` 중 하나를 삭제
- 기존 allocator는 가장 작은 빈 번호를 다시 사용하여 삭제 흔적을 덮을 수 있음

반례 C — symlink:
- `attempt-000N`을 외부 경로 또는 다른 attempt로 symlink
- campaign scanner가 immutable local attempt가 아닌 경로를 읽을 수 있음

보완:
- retry 디렉터리는 전역적으로 `attempt-0001..N`의 연속 sequence여야 한다.
- 번호 공백이 있으면 새 attempt 생성 전에 fail-closed 한다.
- allocator는 검증된 마지막 번호 다음 값만 사용한다.
- `attempt-*`가 symlink 또는 directory가 아닌 entry이면 거부한다.
- active case의 ledger identity(`ledger_sha256 + final event hash + seq`)가 history에서 중복되면 replay/copy로 보고 거부한다.
- shared output root의 다른 case는 기존처럼 자기 case ID로 검증한 후 active campaign 계산에서는 제외한다.

추가 회귀:
- 동일 campaign lock을 다른 프로세스가 보유한 동안 새 cycle 시작 차단
- attempt sequence gap 차단
- 동일 ledger를 복사한 replay attempt 차단
- POSIX symlinked attempt 차단

남는 제한:
- **가장 마지막 attempt 디렉터리 하나만 완전히 삭제**하고 더 높은 번호의 디렉터리가 전혀 없는 경우에는 디렉터리 sequence만으로 과거 tail 존재를 증명할 수 없다. 이 문제를 완전히 막으려면 campaign root 밖의 독립 append-only campaign journal/owner storage가 필요하다.
- SHADOW에서는 이를 운영 무결성 NOTE로 남기며, 현재 단계에서 외부 persistent authority까지 추가하여 다시 대규모 구조 변경 루프를 만들지는 않는다.

### 16. 복구 가능한 ledger append 중단을 campaign history corruption으로 오판하는 문제

append transaction 경계를 다시 시뮬레이션했다.

기존 `case_ledger.append_event()`는 다음 순서의 중단을 복구할 수 있도록 transaction journal을 이미 가지고 있다.

1. pending append transaction 기록
2. ledger event append + fsync
3. anchor 교체
4. pending transaction 제거

하지만 `campaign_history()`는 retry 시 pending transaction을 먼저 복구하지 않고 ledger/anchor를 바로 검증했다.

반례 A:
- `REVIEW_STARTED` 또는 다른 event가 ledger에 append됨
- anchor 교체 직전에 host/process 중단
- pending transaction은 정상이고 복구 가능
- 다음 retry의 history loader는 ledger와 old/missing anchor를 비교하여 corruption으로 차단

반례 B:
- pending transaction은 기록되었지만 ledger append 직전에 중단
- ledger 파일 자체가 아직 없을 수 있음
- 기존 history directory discovery는 pending transaction만 남은 attempt를 아예 보지 못할 수 있음

보완:
- `case_ledger.recover_pending_append_if_present()`를 안전한 public recovery 경로로 추가했다.
- campaign history는 ledger/anchor 검증 전에 pending append transaction을 먼저 복구한다.
- ledger 파일이 아직 없어도 pending transaction만 존재하는 attempt를 history 후보로 포함한다.
- recovery는 기존 ledger lock, transaction digest, event hash chain, pre-ledger SHA-256, HMAC 규칙을 그대로 사용한다.
- transaction 변조, HMAC 불일치, pre-ledger divergence는 계속 fail-closed 한다.

추가 회귀:
- authenticated transaction이 ledger에는 append됐지만 anchor가 없는 상태 → history load가 복구 후 `INTERRUPTED_EMPTY`로 재구성
- pending transaction은 남았지만 ledger write 자체가 사라진 상태 → transaction journal에서 ledger/anchor 복원
- pending transaction payload 변조 → history loader가 `append transaction digest mismatch`로 거부

이 보완으로 **"실제 history corruption"과 "정상적인 append 도중의 crash"를 구분**한다. 복구 가능한 중단 때문에 HUMAN/owner 개입이 필요해지는 불필요한 운영 정지를 줄이면서 기존 fail-closed 무결성은 유지한다.

### 17. shared output root에서 unrelated case의 HMAC/pending 상태가 active case를 차단하는 문제

> **SUPERSEDED:** 이 절의 no-key HMAC skip 결론은 section 20에서 철회되었다. 구조적 case 분류와 불필요한 recovery 방지는 유지하지만, HMAC-protected record는 unrelated여도 key 없이 skip하지 않는다.

앞선 multi-case 병렬화 이후 case 격리성을 다시 시뮬레이션했다.

반례 A:
1. 같은 output root의 case A가 선택적 ledger HMAC key A로 정상 완료
2. case B는 같은 root를 사용하지만 key A를 보유하지 않음
3. 기존 `campaign_history(B)`가 case ID를 건너뛰기 전에 A의 anchor를 key B/무키 상태로 검증
4. A는 B의 budget/history와 무관한데도 `ledger HMAC key unavailable`로 B가 차단될 수 있음

반례 B:
1. case A가 authenticated pending append transaction을 남긴 채 중단
2. case B가 같은 root에서 시작
3. 기존 history loader가 case ID를 확인하기 전에 A의 transaction을 B의 HMAC authority로 복구하려 시도
4. 정상 case B가 unrelated A의 recovery authority 때문에 차단되거나 A의 pending state를 불필요하게 변경할 수 있음

보완:
- ledger가 존재하면 먼저 schema/hash-chain과 단일 case ID 일관성을 검증한다.
- 그 case ID가 active case와 다르면 anchor HMAC 검증과 pending recovery를 수행하지 않고 history budget에서 제외한다.
- ledger가 아직 없고 pending transaction만 있으면 새 `pending_append_case_id()`가 transaction digest, event hash, seq/prev-hash, case-id consistency를 authentication-neutral 방식으로 검증하여 소유 case를 분류한다.
- pending transaction이 active case일 때만 기존 full recovery가 실행되어 HMAC, pre-ledger SHA-256, divergence 검사를 모두 수행한다.
- ledger case ID와 pending transaction case ID가 충돌하면 fail-closed 한다.
- mixed/missing case ID 또는 구조적으로 손상된 ledger는 "unrelated"라고 임의 추정하지 않는다.

회귀:
- case A HMAC ledger + case B no HMAC, same root → B 정상 완료
- case A authenticated pending transaction only + case B same root → B 정상 완료, A transaction bytes/ledger 상태는 변경하지 않음
- active-case HMAC 검증과 pending recovery의 기존 fail-closed 동작은 유지

이 변경은 shared root의 병렬성을 실제 **authority isolation**까지 확장한다. 다른 case의 정상적인 보안 설정 차이가 현재 case의 reviewer 실행이나 budget을 막지 않는다.

### 18. cross-case isolation이 HMAC-protected active history의 relabel 우회가 될 수 있는 문제

> **SUPERSEDED IN PART:** active key가 있을 때의 relabel 방어는 유지된다. 다만 'active key가 없으면 unrelated HMAC을 skip 가능'이라는 당시 결론은 section 20에서 제거되었다.

section 17 보완을 다시 공격적으로 검토했다.

초기 격리안은 ledger의 unkeyed schema/hash chain과 case ID가 정상이고 active case와 다르면 HMAC 검증 전에 skip할 수 있었다. 이 방식만으로는 다음 공격 경계가 생긴다.

반례:
1. active case A의 ledger/anchor는 HMAC-protected
2. 공격자가 ledger의 `case_id`를 B로 바꾸고 모든 `prev_hash/event_hash`를 다시 계산
3. anchor의 case ID, final event hash, ledger SHA-256도 B 기준으로 수정
4. secret HMAC은 계산할 수 없어 기존 값이 남음
5. HMAC 검증보다 먼저 "B는 unrelated"라고 skip하면 A의 과거 worker/remediation budget이 사라져 보일 수 있음

보완:
- active execution이 `MAESTRO_LEDGER_HMAC_KEY`를 제공하면 해당 shared output root를 하나의 HMAC trust domain으로 취급한다.
- unrelated ledger라도 pending transaction이 없으면 anchor를 같은 key로 검증한 후에만 skip한다.
- unrelated pending transaction도 같은 key의 HMAC이 필수이며 `pending_append_case_id(..., require_hmac=True)`에서 인증한다.
- 따라서 서로 다른 HMAC key를 사용하는 case들을 하나의 keyed shared root에 섞는 구성은 fail-closed 한다.
- active HMAC authority가 없는 SHADOW 실행에서는 unrelated HMAC의 key 자체를 요구하지 않되, ledger hash chain, anchor core fields, transaction digest/event hash/case-ID consistency는 계속 검증한다.

회귀:
- HMAC case A + no-key SHADOW case B: structurally valid A를 budget에서 제외하고 B 정상 완료
- active key B가 있는데 root의 case A가 다른 key A를 사용: HMAC mismatch로 reviewer 시작 전 차단
- HMAC-protected case A의 ledger+anchor를 case B로 relabel하고 unkeyed hash를 모두 재계산: 남아 있는 HMAC 불일치로 history reset 차단
- unrelated pending transaction은 active HMAC trust domain에서는 동일 key가 아니면 skip되지 않음

이 보완으로 multi-case throughput 최적화가 HMAC의 anti-tamper 성질을 약화시키지 않도록 경계를 다시 닫았다.

### 19. 서로 다른 case의 concurrent append 중간 상태를 history scanner가 corruption으로 읽는 문제

shared root에서 서로 다른 case의 병렬 실행을 허용한 상태를 실제 파일 경계로 다시 시뮬레이션했다.

`append_event()`는 ledger별 lock 아래에서 transaction journal → ledger append → anchor replace를 수행한다. 하지만 기존 `campaign_history()`는 해당 ledger lock을 잡지 않고 ledger/anchor를 읽었다.

반례:
1. case A가 ledger lock을 잡고 append 수행 중
2. ledger file이 write 중이거나 새 event는 보이지만 anchor 교체 전
3. 동시에 case B가 같은 root에서 history scan
4. B는 A의 일시적인 partial JSON 또는 ledger/anchor mismatch를 영구 corruption으로 오판
5. B의 reviewer는 시작조차 못 하고 불필요한 retry가 발생

보완:
- 각 campaign history entry의 초기 ledger/event/anchor/pending 상태를 읽을 때 해당 ledger의 append lock을 획득한다.
- unrelated case의 구조/HMAC 검증과 skip 판단도 같은 consistent snapshot 안에서 수행한다.
- active case pending transaction은 snapshot 확인 후 기존 recovery 경로로 넘긴다.
- 2초 안에 consistent snapshot lock을 얻지 못하면 `campaign ledger busy during consistent history snapshot`로 reviewer 시작 전에 fail-closed 한다.
- partial write 자체를 durable history corruption으로 기록하지 않는다.

회귀:
- unrelated ledger lock을 잡은 상태에서 ledger bytes를 의도적으로 partial JSON으로 바꿈
- 동시에 다른 case의 history reader 실행
- reader가 즉시 partial JSON을 소비하지 않고 lock 해제까지 대기
- 원래 valid ledger/anchor를 복원 후 reader 정상 완료, unrelated history는 budget에서 제외

### 20. no-key shared-root HMAC skip은 relabel 여부를 판별할 수 없는 근본적 모호성

section 17~18의 HMAC 격리를 다시 공격했다.

초기 정책은 active run에 HMAC key가 없으면 structurally valid unrelated HMAC ledger를 key 없이 skip할 수 있게 했다. 그러나 key가 없는 관찰자는 다음 두 상태를 구분할 수 없다.

- 실제 unrelated HMAC case A
- active case의 HMAC-protected history를 공격자가 case B로 relabel하고 unkeyed hash/ledger SHA만 재계산한 상태

둘 다 HMAC key 없이는 "정말 unrelated"인지 인증할 수 없다. 따라서 no-key skip을 허용하면 HMAC-protected retry/worker history reset 가능성이 남는다.

보완:
- shared output root는 case ID와 무관하게 하나의 ledger-HMAC trust domain으로 취급한다.
- encountered ledger anchor에 HMAC이 있으면, unrelated case라도 해당 key가 없을 때 skip하지 않고 fail-closed 한다.
- pending append transaction에 HMAC이 있으면 `pending_append_case_id()`도 key 없이 분류/skip하지 않는다.
- active key가 있는데 unrelated protected record가 다른 key를 쓰면 HMAC mismatch로 차단한다.
- unkeyed shared-root case들은 기존처럼 서로 독립적으로 병렬 실행 가능하다.
- keyed case와 unkeyed/no-key case를 같은 root에서 섞고 싶다면 별도 output root로 trust domain을 분리해야 한다.

회귀:
- HMAC case A + no-key case B, same root → B reviewer 시작 전 `HMAC key unavailable` 차단
- HMAC pending transaction + no-key unrelated case → transaction을 변형/복구하지 않고 key-unavailable로 차단
- HMAC history를 다른 case ID로 relabel 후 unkeyed hash 전부 재계산 → no-key run도 HMAC key-unavailable로 history reset 차단
- 올바른 key를 제공하면 relabel은 기존대로 HMAC mismatch로 차단

이 수정은 이전 라운드의 availability 우선 판단을 철회한 것이다. HMAC이 등장한 root에서는 case 격리보다 **anti-tamper authority 보존**을 우선한다.

### 21. clean-extracted 검증에서 /proc descendant 종료 확인이 race로 실패하는 문제

최신 exact-HEAD canonical은 통과했지만 clean-extracted package 검증에서 기존 regression test가 한 번 실패했다.

실패:
- `V26CodexFollowupTests.test_validation_group_kills_descendants_after_pass`
- child PID 종료 여부를 `/proc/<pid>/stat`로 확인하는 순간 process가 사라짐
- `Path.read_text()`가 Linux procfs race에서 `ProcessLookupError(ESRCH)`를 발생
- 테스트는 `FileNotFoundError`만 "이미 종료됨"으로 처리하여 실제 성공 조건을 test error로 오판

코드 리딩:
- `tools/run_validation.py::_run_group()`는 passing group 종료 후에도 `_terminate_test_group(group_id)`를 finally에서 실행한다.
- `_terminate_test_group()` 자체도 이미 `ProcessLookupError`를 정상적인 "이미 없음" 상태로 처리한다.
- 따라서 이번 실패는 descendant leak이 아니라 **검증 테스트의 procfs 관측 race**였다.

보완:
- descendant 종료를 확인하는 두 regression loop 모두 `FileNotFoundError`와 `ProcessLookupError`를 동일하게 "process already exited"로 처리한다.
- 실제 process가 살아 있거나 zombie가 아닌 상태는 기존처럼 deadline까지 감시한다.
- validation runner의 kill semantics는 변경하지 않았다.

이 수정은 source authority나 review policy가 아니라 검증 파이프라인의 결정성을 높이는 회귀 보완이다.

### 22. active case의 ledger/anchor와 case-record 사이 torn bundle snapshot

section 19에서는 다른 case의 ledger append 중간 상태를 막았지만 active case의 최종 history reconstruction은 초기 분류 lock을 푼 뒤 다시 ledger/anchor/case-record를 읽고 있었다.

동시에 `ingest_outcome.py`, `ingest_incident.py`, `record_human_decision.py`는 다음처럼 bundle을 여러 파일에 걸쳐 갱신한다.

1. transaction file 확인/생성
2. ledger event append + anchor 갱신
3. case-record/cycle/attestation replace
4. transaction 제거

반례 A — torn read:
- outcome writer가 `OUTCOME_RECORDED`를 ledger에 append
- case-record 교체 직전
- active campaign history가 ledger/anchor는 새 상태, case-record는 이전 상태로 읽음
- bundle semantic validation이 일시적 mismatch를 영구 corruption으로 오판

반례 B — transaction preparation race:
- 두 post-review writer가 동시에 같은 bundle을 읽음
- 둘 다 자기 transaction이 없다고 판단하고 stale case snapshot에서 서로 다른 update를 준비
- finish 단계만 lock하면 transaction 준비/교체 구간의 stale update 경쟁은 남음

보완:
- `case_ledger.py`에 외부 temp control 영역 기반 `case_bundle_lock()` 추가
- lock key는 canonical case-record path SHA-256으로 생성하여 reviewed repo/output tree에 control file을 남기지 않음
- campaign history의 active-case 최종 reconstruction은 `bundle lock → ledger lock` 순서로 ledger/anchor/case-record를 같은 snapshot에서 검증
- pending ledger recovery도 bundle lock 안에서 수행
- outcome/incident/HUMAN writer는 transaction 존재 확인부터 case 읽기, transaction 생성, ledger append, case/cycle replace, transaction cleanup까지 전체 lifecycle을 동일 bundle lock으로 직렬화
- lock order를 항상 bundle → ledger로 고정하여 history/writer 간 교착 가능성을 줄임
- unrelated case의 빠른 classification은 기존 per-ledger lock 경로를 유지

추가 회귀:
- active case bundle lock 동안 case-record를 partial JSON으로 바꾸고 history reader 실행 → reader가 partial file을 소비하지 않고 lock 해제 후 정상 history 재구성
- outcome writer를 bundle lock 바깥 프로세스로 실행하면서 lock을 선점 → writer가 ledger event를 먼저 쓰지 않고 대기, 해제 후 OUTCOME_RECORDED + case-record가 함께 정상 반영
- bundle control path가 reviewed temporary repository 내부가 아님을 확인

이 보완은 review budget 의미를 바꾸지 않고, multi-file case bundle을 실제 transaction boundary와 일치시키는 동시성 보완이다.

### 23. 다중 PC가 같은 shared output을 사용할 때 host-local lock이 무력화되는 문제

현재 구조를 PC1/PC2가 같은 campaign/output storage를 각각 다른 로컬 경로로 mount하는 상황으로 시뮬레이션했다.

기존 문제:
- campaign single-writer lock과 case-bundle lock이 각 호스트의 `%TEMP%` / `/tmp` 아래에 존재
- PC1과 PC2는 같은 case/output을 실행해도 서로의 temp lock을 보지 못함
- 실제 ledger lock도 owner가 PID 하나뿐이어서 원격 호스트 PID를 로컬에서 조회한 뒤 "죽은 PID"로 오판하여 활성 lock을 삭제할 수 있음

반례 A — campaign budget oversubscription:
1. PC1과 PC2가 같은 shared campaign root와 case ID 사용
2. 각자 자기 temp의 case lock 획득
3. 둘 다 같은 history에서 remaining worker budget을 읽음
4. reviewer가 중복 시작되어 campaign-wide 9-call ceiling을 초과할 수 있음

반례 B — attempt allocation collision:
1. 두 호스트가 서로 다른 local temp allocation lock을 획득
2. 둘 다 같은 next `attempt-000N` 계산
3. 디렉터리 생성/실행이 충돌하거나 한쪽이 partial attempt를 남김

반례 C — ledger lock 원격 PID 오판:
1. PC1이 shared ledger의 `.lock`에 자기 PID 기록
2. PC2에서 동일 PID가 존재하지 않음
3. 기존 `_pid_alive(remote_pid)`는 false
4. PC2가 PC1의 active ledger lock을 stale로 오판해 삭제 가능

보완:
- lock owner를 단순 PID에서 `host_id + pid + token` JSON metadata로 변경
- 기본 host ID는 `hostname + node identifier`; 필요하면 `MAESTRO_LOCK_HOST_ID`로 명시 가능
- 동일 host ID의 dead PID만 자동 stale recovery 허용
- 다른 host ID의 lock은 local PID 상태와 무관하게 절대 자동 삭제하지 않음
- lock release 시 자기 host/pid/token이 모두 일치할 때만 unlink하여 교체된 다른 owner lock을 지우지 않음
- owner metadata는 exclusive-create 후 flush/fsync하여 기록
- legacy PID-only / malformed lock은 host identity를 증명할 수 없으므로 자동 회수하지 않음

공유 경로 보완:
- campaign case lock과 allocation lock을 local temp에서 shared campaign root의 `.codediff-control/`로 이동
- root freshness 판단에서 `.codediff-control`을 control metadata로 제외하여 최초 실행 semantics 유지
- case-bundle lock도 case-record와 같은 shared parent의 `.codediff-control/`로 이동
- 따라서 서로 다른 드라이브 문자/경로 표현을 사용하더라도 같은 shared folder를 보는 PC들은 동일 lock file을 경쟁
- actual ledger append lock도 동일한 host-aware owner semantics를 사용

추가 회귀:
- 같은 host ID + 명백히 dead PID lock → 정상 자동 회수
- foreign host ID + 로컬에 존재하지 않는 PID → timeout/fail-closed, lock bytes 보존
- foreign campaign same-case lock → reviewer 시작 전 차단
- foreign allocation lock → 새 attempt 생성 전 차단
- foreign bundle lock → local bundle access 차단
- 서로 다른 case lock은 기존처럼 같은 root에서 병렬 허용

잔여 운영 NOTE:
- remote host가 강제 종료되어 shared lock만 남은 경우, 외부 coordinator 없이 원격 process death를 신뢰성 있게 증명할 수 없다.
- 이 경우 age 기반 자동 삭제는 split-brain을 다시 열 수 있으므로 사용하지 않는다.
- stale foreign lock은 운영자가 공유 스토리지/노드 상태를 확인한 뒤 제거하거나, 향후 외부 lease/coordinator 계층에서 증명된 recovery를 제공해야 한다.
- SHADOW v2.7에서는 fail-closed를 선택하며 자동 retry loop를 만들지 않는다.

### 24. shared control directory cleanup이 waiter와 경합하는 문제

multi-host shared lock 보완 후 exact-HEAD canonical validation에서 실제 회귀가 검출됐다.

실패:
- `test_active_history_waits_for_case_bundle_snapshot`
- `test_outcome_writer_holds_case_bundle_lock_through_bundle_mutation`

원인:
1. owner가 `case-bundle-*.lock`을 해제
2. `case_bundle_lock()` finally가 비어 보이는 `.codediff-control/` 디렉터리를 `rmdir`
3. 동시에 기다리던 다른 thread/process가 다음 exclusive lock file을 생성하려고 함
4. parent directory가 사라져 `FileNotFoundError`
5. lock 자체의 mutual exclusion은 맞지만 control-directory lifecycle이 waiter-safe하지 않았음

보완:
- shared `.codediff-control/` 디렉터리를 runtime 동안 삭제하지 않고 persistent control namespace로 유지
- lock file만 owner token 검증 후 제거
- `.gitignore`에 `**/.codediff-control/` 추가하여 case bundle이 repository 내부에 놓이는 예외 상황에서도 coordination metadata가 source dirtiness를 만들지 않도록 함
- campaign root freshness 판정은 이미 `.codediff-control`을 payload에서 제외하므로 최초/재시도 semantics 유지

이 보완 후 waiter는 parent namespace가 사라지는 race 없이 다음 lock acquisition을 계속할 수 있다.

### 25. 동일 MAESTRO_LOCK_HOST_ID 오배포가 cross-host lock reclaim domain을 합치는 문제

section 23의 multi-host lock을 다시 설정 오류 관점에서 공격했다.

기존 `lock_host_id()`는 `MAESTRO_LOCK_HOST_ID`가 있으면 hostname/node fingerprint를 완전히 대체했다.

반례:
1. PC1과 PC2에 운영 자동화가 같은 `MAESTRO_LOCK_HOST_ID=production-review`를 배포
2. PC1이 shared campaign lock을 보유
3. PC2가 lock owner의 host_id를 자기 값과 동일하다고 판단
4. PC1 PID는 PC2 로컬 process table에는 없음
5. PC2가 PC1의 살아있는 lock을 "same-host dead PID"로 오판하여 삭제 가능
6. same-case reviewer 중복 실행/worker budget oversubscription이 다시 열릴 수 있음

보완:
- 새 `lock_local_fingerprint()`는 hostname + node identifier를 로컬 machine fingerprint로 유지
- `MAESTRO_LOCK_HOST_ID`는 fingerprint를 대체하지 않고 operator namespace/salt로만 사용
- 최종 host_id는 configured namespace와 local fingerprint를 SHA-256으로 결합
- 따라서 같은 configured label을 서로 다른 machine fingerprint에 배포해도 host_id는 다름
- foreign lock stale recovery 규칙은 그대로: 최종 host_id가 완전히 같은 경우에만 local PID liveness를 사용
- 회귀 테스트에서 동일 configured label + 동일 hostname + 서로 다른 node identifier가 서로 다른 host_id를 생성하는지 확인

잔여 NOTE:
- 완전히 복제된 VM처럼 hostname, node identifier, configured namespace까지 모두 동일하게 복제하면 소프트웨어만으로 물리 host 차이를 증명할 수 없다.
- 그런 환경에서는 VM별로 서로 다른 `MAESTRO_LOCK_HOST_ID` namespace를 반드시 부여해야 한다.
- 이 제한은 일반 PC/정상적으로 고유화된 VM에서는 발생하지 않는다.

### 26. .codediff-control symlink/junction이 shared lock namespace를 우회하는 문제

multi-host lock 배치 자체를 filesystem redirect 관점에서 다시 공격했다.

반례:
1. shared campaign root의 `.codediff-control`을 symlink 또는 Windows junction으로 미리 생성
2. target을 host-local path 또는 다른 writable directory로 지정
3. campaign/bundle lock 코드는 해당 path 아래에 lock을 생성
4. 서로 다른 PC가 실질적으로 다른 coordination namespace를 보거나 공격자가 lock namespace를 외부로 이동 가능
5. same-case exclusion/attempt allocation이 다시 split-brain 될 수 있음

보완:
- `ensure_control_dir()` 추가
- 기존 `.codediff-control`이 symlink, junction, non-directory이면 fail-closed
- 새 directory 생성 후에도 type을 다시 확인
- campaign `campaign_control_path()`와 bundle `case_bundle_lock_path()`가 동일 검증 helper 사용
- 정상 real directory만 chmod best-effort 후 사용
- 회귀 테스트에서 campaign control symlink와 bundle control symlink 모두 `unsafe coordination directory`로 거부 확인

잔여 NOTE:
- control directory를 검증 직후 권한 있는 외부 주체가 교체하는 극단적 TOCTOU 공격까지 완전히 막으려면 directory handle/openat 또는 외부 coordinator 수준이 필요하다.
- 현재 SHADOW 위협 모델에서는 pre-existing redirect를 fail-closed로 막고, shared storage ACL로 coordination directory 교체 권한을 제한하는 것을 운영 전제로 둔다.

### 27. same-host PID 재사용이 stale lock을 영구 live로 오판하는 문제

cross-host split-brain 보완 이후 이번에는 같은 PC의 장시간 운영/재부팅 상황을 시뮬레이션했다.

반례:
1. process A가 lock을 잡음
2. A가 비정상 종료되어 lock file이 남음
3. OS가 시간이 지난 뒤 동일 PID를 전혀 다른 process B에 재사용
4. 기존 stale recovery는 host_id가 같고 `_pid_alive(pid)==True`이므로 lock을 live로 판단
5. 실제 owner는 죽었지만 lock이 장기간 회수되지 않아 campaign/bundle/ledger가 불필요하게 중단

보완:
- lock owner metadata에 가능한 플랫폼에서 `process_instance` 추가
- Linux: `/proc/<pid>/stat` start time + kernel boot ID
- Windows: process creation FILETIME
- same-host stale recovery는 recorded process_instance와 현재 PID의 process_instance가 다르면 PID가 살아 있어도 **PID reuse로 판정하여 stale lock 회수**
- process instance를 읽을 수 없는 플랫폼/권한 상태에서는 기존 PID liveness 기반 보수적 동작으로 fallback
- malformed `process_instance` metadata는 자동 회수하지 않고 fail-closed
- unlock은 기존대로 host/pid/token이 모두 일치하는 현재 owner만 수행

회귀:
- same host + 같은 PID + 다른 process_instance + PID alive → old lock 회수 후 새 owner 획득
- malformed process_instance object → 자동 회수 금지, timeout/fail-closed
- 기존 dead same-host PID recovery와 foreign-host non-reclaim 규칙 유지

이 보완은 stale foreign lock 자동 추측을 도입하지 않으면서, **같은 PC 내부의 PID 재사용으로 생기는 불필요한 장기 중단만 줄인다.**

### 28. 두 stale reclaimer의 compare→unlink race가 fresh owner lock을 삭제할 수 있는 문제

PID reuse 보완 이후 stale recovery 자체를 동시 실행 관점에서 다시 공격했다.

기존 흐름:
1. reclaimer A/B가 같은 stale lock을 읽고 둘 다 stale로 판단
2. A가 `_unlink_lock_if_unchanged()`에서 old bytes가 그대로임을 확인
3. B가 먼저 old lock을 삭제하고 새 lock을 획득
4. A가 자신의 check 이후 뒤늦게 path를 unlink
5. A의 unlink가 B의 **fresh lock**을 지울 수 있음
6. A도 새 lock을 획득하면 A/B가 동시에 critical section에 들어가 split-brain 가능

핵심은 내용 비교와 path unlink 사이가 원자적이지 않았다는 점이다.

보완:
- 각 lock path에 대해 `<lock>.reclaim` atomic directory를 stale-reclaimer guard로 사용
- stale deletion을 시도하는 reclaimer들만 이 guard를 경쟁
- guard 획득 후 대상 lock을 다시 읽고 same-host/process-instance/PID 기준으로 stale 여부를 **재평가**
- 재평가 결과가 여전히 stale일 때만 compare-and-unlink 수행
- 다른 reclaimer는 guard가 존재하는 동안 stale deletion을 수행하지 않음
- normal owner acquisition은 guard에 의해 막히지 않으며, 새 owner가 먼저 lock을 만들면 다음 reclaimer의 재평가에서 live owner로 판정되어 삭제되지 않음

회귀:
- reclaim guard를 다른 reclaimer가 보유한 상태에서는 stale lock을 삭제하지 않음
- guard 해제 후 동일 stale lock은 정상 회수
- 두 thread가 같은 stale lock에서 동시에 시작해도 critical section peak concurrency는 1
- 기존 foreign-host non-reclaim, PID-reuse detection, owner-token unlock semantics 유지

잔여 NOTE:
- reclaimer가 `.reclaim` guard 생성 직후 강제 종료되면 guard가 남아 이후 자동 stale deletion을 막을 수 있다.
- 이 상태는 split-brain 대신 fail-closed availability 저하를 선택한 것이며, SHADOW에서는 operator-verified cleanup 대상으로 둔다.
- guard 자체를 age 기반 자동 삭제하면 같은 race를 다른 파일로 옮길 수 있으므로 자동 lease 복구는 추가하지 않는다.

### 29. hostname/NIC 변화가 같은 PC를 foreign host로 고정하는 문제

cross-host split-brain 방어를 유지한 채 운영 중 host identity drift를 시뮬레이션했다.

기존 `lock_local_fingerprint()`는 `hostname + uuid.getnode()` 기반이다.

반례:
1. PC가 lock을 보유한 상태에서 비정상 종료
2. 이후 hostname 변경 또는 NIC 교체/가상 NIC 재생성
3. stale lock의 old `host_id`와 현재 `host_id`가 달라짐
4. 동일한 실제 PC인데도 foreign-host lock으로 분류
5. local process death를 안전하게 확인할 수 있어도 stale lock 자동 회수 불가
6. campaign/bundle/ledger가 operator cleanup 전까지 불필요하게 중단

단일 OS machine-id만 신뢰하는 보완은 복제 VM에서 위험하므로 사용하지 않았다.

최종 보완:
- Windows MachineGuid 또는 Linux `/etc/machine-id`/D-Bus machine-id를 안정 machine source로 사용
- raw 값은 lock metadata에 기록하지 않고 SHA-256 기반 `machine_id`로 저장
- `hostname_id`, `node_id`도 namespace/salt와 함께 해시해 owner metadata에 저장
- exact host_id가 다를 때 same-host로 인정하려면:
  - machine_id 일치 **AND**
  - hostname_id 또는 node_id 중 하나 이상 일치
- 따라서 hostname만 변경되거나 NIC만 변경된 같은 PC는 stale recovery 가능
- machine-id만 같은 clone A/B에서 hostname과 node가 모두 다르면 foreign 유지
- hostname과 NIC가 동시에 모두 바뀐 경우는 machine-id 하나만으로 자동 reclaim하지 않고 fail-closed/manual
- `MAESTRO_LOCK_HOST_ID` namespace는 각 identity component hash에도 포함되어 clone 분리 가능

회귀:
- stable machine + same node + hostname change → old stale lock 회수 성공
- same machine-id clone + different hostname + different node → foreign lock 유지/timeout
- 기존 exact host, PID-reuse, foreign-host, stale-reclaimer guard semantics 유지

이 수정은 split-brain 허용 범위를 넓히지 않고, 정상적인 단일 식별자 변화에서만 availability를 회복한다.

### 30. L1/L2가 같은 family/axis의 서로 다른 파일 결함을 각각 지적하면 disagreement가 사라지는 문제

앞선 broad-family repeat 보완을 reviewer 간 교차판정 관점에서 다시 시뮬레이션했다.

반례:
1. L1: `src/a.py`의 `CORRECTNESS / correctness / major`
2. L2: `src/b.py`의 `CORRECTNESS / correctness / major`
3. 두 finding은 실제로 서로 다른 파일/결함
4. 기존 `disagreement()`는 `severity + failure_family + axis`만 비교
5. 두 set이 동일해져 `l1_l2_disagreement=false`
6. 다른 adversarial 신호가 없으면 L2에서 종료 가능

영향:
- 서로 다른 결함을 두 reviewer가 각각 보고했는데도 “합의”로 오인할 수 있음
- 필요한 adversarial adjudication이 생략될 수 있음
- 특히 broad failure family가 많은 correctness/test 계열에서 authority path가 실제보다 짧아질 수 있음

보완:
- reviewer disagreement도 campaign repeat와 동일한 `material_finding_key()` identity를 사용
- 비교 단위는 `severity + normalized(failure_family, axis, path)`
- 같은 family/axis라도 path가 다르면 disagreement
- 동일 path/identity라도 severity가 달라지면 기존처럼 disagreement 유지

회귀:
- same family/axis/severity + different path → disagreement=true
- same defect + `src/a.py` vs `./src/a.py` → disagreement=false

### 31. 경로 별칭으로 same-material repeat 제한을 우회할 수 있는 문제

material repeat key의 path를 raw reviewer 문자열 그대로 사용하면 동일 파일도 표기 방식에 따라 다른 key가 된다.

반례:
1. attempt 1: `src/module.py`
2. attempt 2: `./src/module.py`
3. 또는 Windows-style `src\\module.py`
4. 실제로는 같은 repository path인데 기존 key digest는 서로 다름
5. same-material repeat limit가 동일 결함을 새 결함으로 인식하여 자동 보완 루프가 한 번 더 진행될 수 있음

보완:
- `material_finding_key()`에서 policy용 repository path normalization을 적용
- `./` prefix 제거, slash separator 정규화, unsafe traversal은 fail-closed
- Git object 조회용 exact path에는 이 정규화 값을 재사용하지 않음
- disagreement와 repeat accounting이 동일한 정규화 identity를 공유

회귀:
- `src/module.py`, `./src/module.py`, `src\\module.py`가 같은 material finding key를 생성
- 다른 실제 path는 계속 다른 identity로 유지

이 두 보완은 review 단계를 무조건 늘리는 변경이 아니다. **서로 다른 결함은 disagreement로 분리하고, 같은 결함의 표기 차이는 하나로 합쳐** 불필요한 반복과 과소 에스컬레이션을 동시에 줄인다.

### 32. Leonardo calibration이 서로 다른 material finding을 FINDINGS라는 이유만으로 agreement로 학습하는 문제

런타임 disagreement를 path-aware identity로 고친 뒤 장기 calibration 경로를 다시 시뮬레이션했다.

반례:
1. L1 material key = `finding:path-a`
2. L2 material key = `finding:path-b`
3. 둘 다 material finding이 있으므로 `material_state()==FINDINGS`
4. 기존 calibration은 state 문자열만 비교하여 L1을 final L2와 agreement로 집계
5. downstream `route_case`도 두 단계가 모두 FINDINGS이면 disagreement reason을 만들지 않음

영향:
- 실제로 서로 다른 결함을 보고한 reviewer를 “정확히 일치”한 것으로 학습
- model/worker agreement rate가 과대평가될 수 있음
- 장기적으로 reviewer routing/calibration 판단이 잘못된 방향으로 수렴할 수 있음

보완:
- v2.7의 `material_finding_keys`가 존재하면 calibration agreement/reversal을 exact key-set identity로 비교
- 과거/부분 레코드처럼 material key가 없으면 state-only 비교로 backward compatibility 유지
- `route_case`의 L1/L2 disagreement도 같은 key-set 의미론으로 통일
- NOTE_ONLY는 기존처럼 material PASS로 유지

회귀:
- L1/L2가 모두 FINDINGS이지만 key set이 다름 → agreement=0, reversal=1
- 같은 case의 routing reason에 `L1_L2_DISAGREEMENT` 포함
- legacy key-missing record는 기존 state-only 의미론 유지

이 보완으로 런타임 authority path와 Leonardo 장기 학습이 같은 material identity를 사용하게 된다.

### 33. Windows path alias 보완이 Git literal backslash 파일을 같은 finding으로 합치는 문제

#31에서 `src/module.py`와 `src\\module.py`를 같은 경로 표기로 취급했지만, Git의 repository path 의미론에서는 backslash가 separator가 아니라 **파일명에 포함될 수 있는 literal 문자**다.

반례:
1. 저장소에 `src/module.py`와 `src\\module.py`가 둘 다 존재
2. L1은 전자의 결함, L2는 후자의 결함을 보고
3. 기존 `material_finding_key()`가 policy path normalization을 재사용하여 backslash를 slash로 변환
4. 두 개의 실제 다른 Git path가 같은 finding key로 합쳐짐
5. L1/L2 disagreement가 사라지거나 same-material repeat로 잘못 집계될 수 있음

보완:
- reviewer finding identity 전용 `canonical_finding_path()` 도입
- Git exact path semantics를 따르며 backslash를 slash로 바꾸지 않음
- `./` presentation prefix만 안전하게 제거
- task `changed_paths`에 exact path가 있으면 exact spelling을 authority로 사용
- 기존 policy matcher의 backslash normalization은 protected-path 방어 목적에만 남기고 finding identity에는 사용하지 않음

회귀:
- `src/module.py`와 `src\\module.py`는 서로 다른 material finding key
- `src/module.py`와 `./src/module.py`는 같은 identity
- 두 literal Git path를 L1/L2가 각각 보고하면 disagreement=true

### 34. unsafe finding path가 reviewer validation 뒤에서 HARNESS_EXCEPTION으로 변하는 문제

기존 reviewer-stage schema는 finding `path`가 non-empty string인지까지만 확인했다.

반례:
1. reviewer가 `../outside.py`, absolute path, Windows drive path 등을 finding path로 반환
2. stage validation 통과
3. 이후 material identity 계산에서 path normalization 예외 발생
4. reviewer 계약 위반이 `REVIEW_INVALID_RESULT`가 아니라 일반 harness exception으로 분류될 수 있음

보완:
- stage semantic validation에서 finding path를 즉시 검증
- NUL, absolute/UNC/drive path, empty/`.`/`..` repository segment를 fail-closed
- identity 계산 전에 invalid reviewer result로 차단
- path validation과 material identity가 동일 helper를 사용하여 validation/use 의미론을 일치시킴

회귀:
- `../src/a.py` → invalid finding path
- `C:\\repo\\src\\a.py` → invalid finding path
- 정상 repository-relative path는 계속 허용

### 35. changed_paths 밖의 무관한 finding이 escalation/calibration을 오염할 수 있는 문제

review worker 지침은 “변경이 활성화하거나 악화시키지 않은 pre-existing issue를 보고하지 말라”고 되어 있었지만 harness가 이를 강제하지 않았다.

반례:
1. 실제 변경은 `src/a.py`
2. reviewer가 무관한 `src/unrelated.py`의 major finding을 반환
3. 기존 stage validation은 path 범위를 확인하지 않아 결과를 수락
4. L2/adversarial escalation, campaign repeat budget, Leonardo calibration에 무관한 finding이 들어갈 수 있음
5. 반복 시 불필요한 검토 시간 또는 false HUMAN escalation 가능

보완:
- changed file finding은 task `changed_paths`의 exact Git path(또는 `./` presentation alias)여야 함
- changed_paths 밖 finding은 **`preexisting=true` AND `activated_or_worsened=true`**일 때만 허용
- 따라서 cross-file impact는 보존하면서 unrelated pre-existing issue는 차단
- reviewer worker core에도 exact `changed_paths` spelling과 off-diff 예외 규칙을 명시

회귀:
- changed path `./src/a.py` → 허용
- unrelated `src/other.py` + preexisting=false → 거부
- unrelated `src/other.py` + preexisting=true + activated_or_worsened=true → 허용
- traversal path → 범위 예외 여부와 무관하게 거부

이번 보완은 reviewer가 볼 수 있는 결함 범위를 단순히 diff line으로 좁히지 않는다. **직접 변경된 파일 + 변경으로 실제 활성화/악화된 기존 코드**까지는 유지하되, 그 밖의 무관한 finding이 리뷰 예산과 Leonardo 학습을 흔드는 경로만 제거한다.

### 36. Windows absolute-path heuristic가 exact changed Git filename을 오탐하는 문제

Git exact path 보존을 다시 검증하면서 host-path 차단 순서의 반대 경계를 확인했다.

반례:
1. Linux 저장소의 실제 tracked filename이 literal `C:\\literal.py`
2. task `changed_paths`에도 exact 동일 문자열이 존재
3. host-path heuristic가 exact task authority보다 먼저 실행되면 Windows drive path처럼 보여 invalid 처리
4. 실제 changed Git file의 정당한 finding이 차단될 수 있음

보완:
- NUL, leading `/`, empty/`.`/`..` segment 같은 Git-구조상 unsafe 조건은 항상 먼저 차단
- 그 다음 task `changed_paths` exact/canonical-`./` match를 authority로 인정
- exact task path가 아닌 경우에만 Windows drive/UNC 형태를 host absolute path로 거부

회귀:
- task 밖 `C:\\repo\\src\\a.py` → invalid host path
- exact changed path인 literal `C:\\literal.py` → 허용

따라서 path 검증은 host OS 문법을 Git identity 위에 덮어쓰지 않고, **task가 증명한 exact Git path를 우선**한다.

### 37. 새 path-scope 계약이 내장 mock reviewer의 고정 경로를 실제 invalid result로 드러낸 회귀

#35 보완 후 canonical full validation에서 다수 기존 review-cycle 테스트가 `REVIEW_INVALID_RESULT`로 실패했다.

원인:
- production contract는 finding path를 task `changed_paths`에 묶도록 강화됨
- 그러나 `tools/mock_reviewer.py`는 과거부터 모든 finding에 고정 `src/example.py`를 사용
- 대부분의 test fixture 실제 변경 path는 `a.py` 등 다른 경로
- 따라서 새 validator가 mock output을 올바르게 범위 밖 finding으로 거부
- downstream triage/budget/recovery 테스트가 본래 검증하려던 단계에 도달하기 전에 차단됨

보완:
- mock reviewer는 task의 첫 `changed_paths` 값을 finding path로 사용
- changed path가 없는 synthetic task에만 기존 `src/example.py` fallback 유지
- major/minor/nit/novel/security/test-integrity/unsafe-output mock mode 모두 동일 path binding 적용
- production validator를 느슨하게 되돌리지 않음

실행 결과가 보여준 의미:
- 새 path-scope 검증은 실제로 enforcement되고 있었음
- 실패는 policy false positive가 아니라 test double의 계약 불일치였음
- mock도 production reviewer와 동일 output contract를 따르게 되어 회귀 테스트의 신뢰도가 오히려 높아짐

이 항목은 보안 규칙을 테스트 때문에 완화하지 않고 **test double을 실제 계약에 맞추는 방향**으로 해결한다.

### 38. runtime은 severity disagreement인데 Leonardo calibration/route는 agreement로 학습하는 문제

#30~#32에서 path-aware material identity를 도입했지만 runtime과 장기 기록이 아직 완전히 같지 않았다.

반례:
1. L1: `SECURITY-CRITICAL`, 같은 axis/path, severity=`major`
2. L2: 같은 failure family/axis/path, severity=`minor`
3. 강제-review family이므로 minor도 NOTE_ONLY가 아니라 material finding
4. runtime `disagreement()`는 `severity + material_finding_key`를 비교하므로 disagreement=true
5. case-record에는 material key만 저장
6. calibration/route는 같은 key로 보아 agreement=true

영향:
- 실제 authority path에서는 adversarial adjudication이 필요했는데 장기 Leonardo 지표는 합의로 기록
- model/worker agreement rate 과대평가
- 같은 case를 후속 routing할 때 runtime과 다른 이유 집합을 만들 수 있음

보완:
- retry identity인 `material_finding_key`와 review agreement identity를 분리
- `material_finding_signature = severity|material_finding_key`를 harness가 결정적으로 계산
- case-record에 optional `material_finding_signatures`를 저장
- calibration과 route는 양쪽 row에 signature가 있으면 동일 signature multiset을 비교
- campaign retry budget은 기존 key만 계속 사용하여 severity 재평가가 retry budget을 초기화하지 않음

회귀:
- 같은 key의 major vs forced-material minor → runtime disagreement=true
- persisted signature 비교에서도 disagreement=true
- route reason에 `L1_L2_DISAGREEMENT` 유지

### 39. set 비교가 같은 material key의 finding 개수 차이를 숨기는 문제

기존 runtime disagreement는 set을 사용했다.

반례:
1. L1이 같은 file/family/axis에서 material finding 두 개를 보고
2. L2가 그중 하나만 보고
3. 두 finding이 현재 coarse material key로 충돌
4. `{severity,key}` set은 양쪽 모두 원소 하나가 되어 agreement 처리

완전한 semantic defect identifier 없이 두 finding의 의미 자체를 안정적으로 구분할 수는 없지만, 적어도 **개수 손실**까지 허용할 이유는 없다.

보완:
- runtime agreement를 set이 아니라 정렬된 signature list, 즉 multiset으로 비교
- case-record `material_finding_signatures`도 duplicate를 허용하여 multiplicity 보존
- pre-signature v2.7 row도 `material_finding_keys + material_finding_count`를 coarse identity로 비교
- 따라서 같은 key 2개 vs 1개는 runtime/calibration/route 모두 disagreement

회귀:
- 동일 signature 두 개 vs 한 개 → disagreement=true
- retry budget은 여전히 unique material key 기준이므로 같은 coarse defect가 여러 번 표현됐다고 자동 remediation 횟수가 늘어나지 않음

### 40. 새 signature row와 기존 key-only row가 섞일 때 형식 차이만으로 false disagreement가 생길 수 있는 문제

severity-aware signature 초안을 적용한 뒤 upgrade/resume 호환성을 다시 시뮬레이션했다.

반례:
1. 한 row는 새 `material_finding_signatures` 보유
2. 다른 row는 기존 v2.7 `material_finding_keys`만 보유
3. 실제 material key/count는 동일
4. representation 자체를 직접 비교하면 `severity-signature`와 `key` 형식이 다르다는 이유만으로 disagreement

보완:
- 양쪽 모두 새 signature를 가진 경우에만 severity-aware exact 비교
- 한쪽이라도 pre-signature row이면 양쪽이 공통으로 가진 `key set + material_finding_count` 수준으로 downgrade 비교
- 아주 오래된 identity-less row는 기존 state-only compatibility 유지
- case-record validator는 signature가 존재하는 신규 row에서 signature count, key 집합, major/blocker count의 상호 정합성을 검증

회귀:
- new signature row vs 동일한 legacy key/count row → agreement
- legacy same-key count 2 vs count 1 → disagreement
- malformed persisted signature count/key/severity count → case semantic validation failure

### 잔여 NOTE

이번 보완으로 기존 NOTE의 가장 위험한 부분인 **severity 손실과 multiplicity 손실**은 제거했다. 다만 같은 file/family/axis에서 동일 severity로 발생한 서로 다른 두 결함을 reviewer들이 각각 하나씩 보고한 경우처럼, 개수까지 같은 완전한 coarse-key collision은 아직 구분할 수 없다.

이를 해소하려면 claim 문구 hash처럼 불안정한 값을 쓰는 대신 reviewer 간/재시도 간 안정적인 semantic defect locator 계약이 필요하다. 현재 즉시 authority bypass나 무한 retry를 만드는 경로는 아니므로 schema-level 후속 설계 항목으로 유지한다.

### 41. calibration 결과의 interpretation 문구가 새 agreement 의미론과 불일치

#38~#40 보완 후 출력 JSON의 설명 문자열을 다시 확인했다. 계산 로직은 signature/key+count 계층으로 바뀌었지만 `interpretation`은 여전히 “material finding state를 사용한다”고 설명하고 있었다.

영향:
- 수치 자체는 맞아도 운영자가 agreement/reversal을 단순 PASS/FINDINGS 상태 비교로 오해할 수 있음
- Leonardo 장기 지표의 감사 가능성과 설명력이 떨어짐

보완:
- 양쪽 signature 존재 시 severity-aware signature 비교
- pre-signature v2.7은 key+count 비교
- identity-less legacy만 state-only 비교
라는 실제 우선순위를 calibration output 설명에 그대로 반영했다.

### 42. signed ledger의 HMAC 요구를 anchor 자기신고만으로 판단하는 문제

외부 FULL 리뷰 M1을 실제 코드 경로에 대입했다. 기존 일부 경로는 `anchor.hmac_sha256` 유무를 `require_hmac` 결정에 다시 사용했기 때문에, 공격자가 ledger와 anchor를 함께 다시 만든 뒤 HMAC 필드를 제거하면 키 없는 SHADOW 검증에서 과거 signed-mode 사실을 복원할 수 없었다.

보완:
- ledger마다 anchor와 분리된 sticky `case-events.auth.json` witness를 생성
- 한 번 `hmac_required=true`가 되면 정상 API로 false downgrade 불가
- `validate_anchor()`, append-journal recovery, case-bundle 검증이 anchor 자기신고가 아니라 witness를 자동 참조
- immutable case-bank로 라우팅할 때 auth witness도 ledger/anchor와 함께 복사
- `key_id`가 남아 있으면 HMAC requirement로 취급
- 로컬 witness까지 삭제/변조 가능한 공격에 대비해 `MAESTRO_LEDGER_EXPECT_KEY_ID` 및 validation CLI `--expected-key-id`를 외부 expectation 경계로 제공

한계:
- HMAC key도 외부 expectation도 없고 공격자가 ledger/anchor/witness를 모두 다시 쓸 수 있으면, 과거에 signed history였다는 사실은 로컬 파일만으로 암호학적으로 증명할 수 없다.
- 따라서 ENFORCED는 기존처럼 HMAC key를 요구하고, 강한 historical non-downgrade가 필요한 운영은 외부 durable witness/storage boundary를 유지해야 한다.

### 43. keyless recovery journal을 authenticated라고 표현한 문제

외부 FULL 리뷰 M2를 재현했다. HMAC가 없는 append transaction은 transaction digest와 event hash는 검증하지만, 동일 권한으로 파일을 다시 쓸 수 있는 공격자를 상대로 출처 인증을 제공하지 않는다.

보완:
- signed-history witness 또는 외부 expected key ID가 있으면 unsigned/missing-HMAC transaction을 fail-closed
- transaction `key_id` 자체도 HMAC requirement signal로 사용
- 문서/CHANGELOG에서 journal 기본 성격을 `digest-bound integrity`로 수정
- “authenticated recovery journal” 표현은 HMAC authority가 구성된 경우에만 사용

따라서 unsigned SHADOW journal은 deterministic crash recovery + integrity metadata이지 cryptographic authentication이 아니다.

### 44. pending event의 torn JSONL tail을 복구하지 못하는 문제

외부 FULL 리뷰 M3의 line-mid-write 반례를 적용했다.

기존:
1. append transaction durable
2. JSONL event write가 일부 bytes만 기록
3. 재기동 후 `load_events()`가 먼저 실행
4. `JSONDecodeError`로 복구 진입 자체가 중단

보완:
- pending transaction의 exact event bytes를 기준으로 현재 ledger tail이 그 event의 prefix인지 검사
- prefix 제거 후 남은 bytes SHA-256이 `pre_ledger_sha256`와 정확히 일치할 때만 truncate
- truncate fsync 후 pending event 전체를 다시 기록
- unrelated/malformed tail은 추측 수리하지 않고 typed `LedgerTornWriteError`로 fail-closed

회귀:
- exact half-event tail → 정상 recovery
- pending event prefix가 아닌 garbage tail → typed failure

### 45. recovery가 동일 type/payload의 의도적 두 번째 이벤트를 retry로 삼키는 문제

외부 FULL 리뷰 L1의 반례는 payload 동일성만으로 retry identity를 추론하기 때문에 발생했다.

보완:
- append transaction에 optional `event_instance_id` 추가
- 같은 instance ID로 재요청한 경우에만 recovered event를 idempotent retry로 반환
- 다른 instance ID 또는 instance ID가 없는 새 요청은 type/payload가 같아도 별도 event/seq로 append
- review cycle, HUMAN decision, outcome, incident, standard candidate 등 내부 mutation 경로는 stable instance ID를 사용

이제 “동일 데이터”와 “동일 요청”을 구분한다.

### 46. package receipt와 최신 검증 문서의 provenance 연결 부족

외부 FULL 리뷰 L2에서 package 내부에 `.git`이 없어 HEAD/Actions run을 독립적으로 연결하기 어렵다는 점을 확인했다.

보완:
- source-package receipt에 `validation_run_id`, `validation_run_attempt`, `validation_workflow_ref` 추가
- CI가 이 값을 GitHub Actions 환경에서 명시적으로 기록
- receipt self-digest가 HEAD/package/manifest/run metadata를 하나의 traceability record로 묶음
- 단, self-digest만으로 GitHub run의 실재를 증명하지는 않으며 GitHub artifact/run metadata가 외부 확인 근거임을 문서화
- 검증 보고서의 테스트 수/manifest entry/HEAD/run은 최종 Latest-HEAD CI 결과로 다시 고정

### 이번 외부 FULL 리뷰 반영 판정

- M1: **보완됨(외부 expectation이 있을 때 강한 fail-closed, 로컬 전부 변조 한계는 명시)**
- M2: **보완됨/표현 정정** — unsigned mode는 authentication으로 주장하지 않음
- M3: **보완됨** — exact torn-tail recovery + typed failure
- L1: **보완됨** — event-instance identity 도입
- L2: **보완 진행** — receipt CI traceability 반영, 최종 CI 수치로 문서 재고정 예정

### 47. CI traceability 필드를 같은 v2.7 receipt에서 필수화하면 기존 receipt가 깨지는 문제

L2 보완으로 Actions run metadata를 source-package receipt에 추가한 뒤 migration 시나리오를 다시 검토했다.

반례:
1. 기존 v2.7 receipt에는 `validation_run_id` / `validation_run_attempt` / `validation_workflow_ref`가 없음
2. 동일 `schema_version: 2.7`에서 이 세 필드를 required로 바꾸면 과거에 정상 발행된 receipt가 schema/semantic validation에서 실패
3. traceability 개선이 기존 배포물 검증을 깨뜨리는 역회귀 발생

보완:
- 새 receipt 생성기는 세 traceability 필드를 계속 기록
- schema의 required 집합은 기존 v2.7 필드 집합을 유지하고 새 세 필드는 optional extension으로 처리
- semantic validator도 기존 required 필드가 모두 존재하고 unknown field가 없으면 허용
- run ID/attempt는 둘 중 하나만 있는 경우에는 계속 거부
- 기존 receipt에서 세 필드를 제거하고 digest를 재계산한 회귀 fixture가 schema + semantic validation을 모두 통과하는지 확인

이로써 CI provenance 강화가 기존 v2.7 package receipt 읽기 호환성을 파괴하지 않는다.

### 48. 외부 expected key ID를 켜면 내부 writer의 고정 key_id가 정상 HMAC 쓰기를 막는 문제

M1 보완으로 `MAESTRO_LEDGER_EXPECT_KEY_ID`를 추가한 뒤 실제 review-cycle 쓰기 경로를 다시 시뮬레이션했다.

반례:
1. 운영자가 HMAC key와 `MAESTRO_LEDGER_EXPECT_KEY_ID=key-v1`을 설정
2. validator는 `key-v1`을 기대
3. 일부 writer는 anchor/transaction `key_id`로 고정 문자열 `MAESTRO_LEDGER_HMAC_KEY`를 명시
4. 외부 expectation과 writer가 서로 충돌해 정상 signed append가 fail-closed

보완:
- `append_event()`는 HMAC key가 호출 인자로 직접 전달된 경우에도 key_id가 비어 있으면 external expected key ID를 기본값으로 사용
- review cycle, HUMAN decision, outcome/incident writer가 `MAESTRO_LEDGER_EXPECT_KEY_ID`를 우선 key ID로 사용
- expectation이 없을 때는 기존 `MAESTRO_LEDGER_HMAC_KEY` 식별자 호환 유지
- 실제 review-cycle subprocess를 `MAESTRO_LEDGER_HMAC_KEY + MAESTRO_LEDGER_EXPECT_KEY_ID=key-v1`로 실행해 anchor/witness의 key_id가 `key-v1`이고 HMAC이 생성되는 회귀 테스트 추가

이로써 M1의 외부 expectation 기능이 검증 전용 장식이 아니라 실제 write/read 경로에서 사용할 수 있는 운영 기능이 된다.

### 49. Pending ledger 복구에서 동일 event_instance_id의 변경된 요청이 묵살되는 문제

재현 경로 (정적 흐름 분석 + 회귀 테스트 추가):
1. 첫 요청이 `event_instance_id=stable-id`, `CASE_OPENED`, `payload={"v":1}`로 append를 시작
2. JSONL은 기록됐지만 anchor 작성 직전에 예외가 발생하여 pending journal만 남음
3. 다른 요청이 같은 `stable-id`를 재사용하면서 case/type/payload 또는 명시 timestamp를 변경
4. 기존 구현은 `event_instance_id` 일치만 검사하고 recovery 결과를 즉시 반환하여 변경된 새 요청을 조용히 무시

대응:
- pending 복구 완료 후에도 동일 instance ID에 대해 `case_id`, `event_type`, `payload`, caller가 명시한 `timestamp`를 비교
- 하나라도 다르면 `LedgerRecoveryError(code=EVENT_INSTANCE_CONFLICT)`로 fail-closed
- 4개 충돌 변형과 복구 후 원본 이벤트/anchor 정합성 검사를 회귀 테스트로 추가
- 기존 동일 ID + 동일 event 요청의 정상 재시도 동작은 유지

범위 주의:
- 현재 instance ID는 pending journal에만 유지되므로 **성공적으로 완료되어 journal이 제거된 후** 동일 ID를 재사용한 요청에는 durable dedup을 제공하지 않는다. 이를 일반적 exactly-once 보장으로 홍보해서는 안 된다.
- 완료 후 replay까지 막으려면 이벤트 스키마의 버전드 확장 또는 HMAC/anchor로 바인딩된 durable receipt/index를 설계하고 레거시 migration/거버넌스 검증을 거쳐야 한다.
- 이번 수정은 좁은 정합성 경계를 보완하는 1회 배치이며, 자동 재수정 루프나 ENFORCED 승격은 수행하지 않는다.

### 50. 이전 #49 회귀 테스트에서 cross-case 충돌의 실제 검증 순서를 잘못 기대

GitHub Actions #784 (HEAD `8c047b77a459`)는 canonical validation 중 `tests.test_v27_hardening` 단위 그룹에서 실패했다. case ID가 `OTHER`인 테스트는 `EVENT_INSTANCE_CONFLICT`에 도달하기 전에 sticky witness의 `case_id` 검사에서 `ValueError: ledger auth witness case_id mismatch`로 차단되었다. 이는 인증 경계를 지키는 동작이다.

대응:
- 동일 case ID에서 payload/type/timestamp가 충돌하는 경로는 `EVENT_INSTANCE_CONFLICT`로 검증.
- 다른 case ID는 별도 fail-closed 경계로 검증하고 기존 pending transaction/anchor 상태가 변하지 않는지 확인.
- 인증 경계를 통과시키려고 코어 코드를 약화하지 않음.

### 51. 실패한 HMAC 모드 전환이 signed-required witness를 먼저 기록하는 문제

정적 코드 경로 시뮬레이션:
1. unsigned ledger와 unsigned anchor, `hmac_required=false` witness가 정상 존재.
2. HMAC key를 전달해 append를 호출.
3. 기존 순서는 anchor HMAC 검증보다 먼저 `ensure_auth_witness(..., True)`를 호출해 sticky witness를 변경.
4. unsigned anchor는 signed 검증에 실패하므로 append는 실패하지만, witness는 signed-required로 남아 기존 정상 unsigned append까지 차단.

더 위험한 변형은 unsigned pending journal이 있는데 새 요청에 HMAC key를 주거나, signed pending journal의 witness가 사라진 뒤 위조된 HMAC을 넣는 경우다.

대응:
- 기존 ledger에서 anchor가 사라졌고 복구 journal이 없으면 witness 작성 이전에 차단.
- 기존 unsigned ledger를 일반 append로 signed 상태로 전환하려는 시도는 명시적 migration 요구로 사전 차단.
- pending 상태에서 signed-mode 전환을 시도하면 기존 signed witness를 확인하거나, journal HMAC을 **실제로 검증**한 후에만 witness 상태 변경 허용.
- 4개 신규 회귀: 정상 unsigned ledger 전환 실패 후 쓰기 재개, unsigned pending 보호, 위조된 signed pending/witness 누락, preexisting anchorless 파일.
- 범위: 일반 append의 예기치 않은 witness 변경 차단이며 운영자 승인된 과거 signed migration을 새로 자동화하지 않는다.

판정: 운영 중 쓰기 거부 상태를 지속시키는 결함으로 MATERIAL, 단일 묶음 수정. CI 성공 여부와 독립 검증은 최신 HEAD에서 확인한다. 작은 NOTE_ONLY 항목을 추가 자동 수정 루프에 넣지 않는다.

### 52. 서명처럼 보이는 anchor로 signed witness가 선기록되는 경계

최신 post-#51 구현은 `visible_anchor_hmac`가 진짜 MAC 검증 완료를 뜻하지 않는데도, 이 truthy marker로 HMAC preflight를 생략했다. 공격자가 기존 unsigned anchor의 `hmac_sha256`을 가짜 문자열로 바꾸면, 이후 append가 실패하더라도 signed-required witness가 남아 정상 복구를 차단할 수 있었다. 별도로 signed anchor의 witness가 없는 경우 요청 key_id의 drift가 anchor 검증보다 먼저 witness를 오염시키는 문제도 있었다.

보완: 기존 ledger/anchor는 실제 HMAC·hash-chain·key-ID 검증을 통과한 뒤 witness 변경 허용. pending journal이 있으면 anchor가 구버전 상태일 수 있으므로 journal을 먼저 검증하고 key ID drift를 막음. 회귀 시나리오: forged HMAC marker, 잘못된 key-ID 복구, unsigned pending + forged marker.

### 53. 신규 ledger 이벤트의 스키마/직렬화 검증 누락

기존 append writer는 앞선 이벤트를 검증하지만 새로 쓸 `event_type`, `case_id`, `payload`를 파일에 쓰기 전에 스키마 검증하지 않았다. 무효 이벤트 타입이나 비직렬화 payload가 들어가면 원장/append journal에 복구 불가능한 데이터를 남길 수 있었다.

보완: 새 이벤트 입력을 v2.4 schema 및 canonical JSON 직렬화에 대해 **파일 생성 전에** 검증. 새 ledger와 기존 정상 ledger에 대한 회귀 추가.

범위: 이 경계는 코드 기반 시뮬레이션에서 도출한 MATERIAL 결함이며 새로운 실행 테스트는 최신 GitHub Actions로 검증할 것. ENFORCED로 자동 승격하지 않음.

### 54. Pending 복구가 기존 anchor 변조 증거를 새 정상 anchor로 덮어쓰는 문제

정확한 기준 HEAD는 `47fb7544a7b8` (#787 FULL PASS). 중단 경로: 기존 이벤트 seq=1의 anchor가 정상인 상태에서 seq=2 append가 JSONL까지 완료되었지만 새 anchor 저장 전에 중단. 저장장치 오류/위조로 기존 anchor의 HMAC·seq/ledger digest가 손상되거나 파일이 삭제됨. 과거 `_recover_pending_append()`는 journal과 ledger만 확인하고 기존 anchor를 읽지 않은 채 새 anchor를 써서 변조 증거를 소거했다.

수정은 pending transaction 검증 직후, torn-tail 수정 직전에 기존 anchor를 독립 검증한다. 허용하는 anchor는 pre-append(seq=n)와 post-append(seq=n+1, anchor 저장 후 journal 제거 직전 중단) 두 상태뿐이다. 기존 이력이 있을 때 anchor 누락은 `APPEND_ANCHOR_INVALID`로 차단하고, 최초 이벤트는 anchor가 없을 수 있다. pending event 자체에도 v2.4 schema 검사를 적용한다.

회귀 4개: signed anchor HMAC 위조 시 바이트·journal 무변경, 선행 anchor 삭제 차단 및 복원 후 재개, 정당한 post-anchor 중단 복구에서 중복 append 없음, 스키마가 유효하지 않은 unsigned journal 복구 사전 차단. HEAD별 CI 검증을 완료하기 전에는 결과를 PASS라 부르지 않는다.

### 55. 일반 append 재시도에서 witness 없는 변조 anchor를 선기록으로 오염하는 문제

54번의 직접 복구 `_recover_pending_append()`는 검증을 강화했으나 `append_event()`는 유효한 pending journal을 찾으면 기존 anchor 확인 전 `ensure_auth_witness()`를 호출했다. 이전 signed history의 witness가 유실되고 anchor HMAC이 손상된 경우, 복구 자체는 `APPEND_ANCHOR_INVALID`로 막히지만 실패한 재시도에서 signed witness를 먼저 새로 작성하는 side effect가 발생할 수 있었다.

보완: `append_event()`의 pending preflight에도 54번 anchor snapshot 검증을 적용한 후에만 `ensure_auth_witness()`를 허용한다. 새로운 회귀 테스트는 signed history + pending crash + witness 누락 + 가짜 anchor HMAC 조합에서 실패 시 witness/anchor/journal/ledger 바이트가 그대로임을 확인하고, anchor 복원 뒤 정상 복구 및 witness 재생성을 확인한다.

### 56. 단독 ledger 검사에서 생략된 case ID가 혼합 이벤트를 놓침

기준 HEAD `4002f8800fec6b33152ce3c9cdd467a20108fdb2`, GitHub Actions #789 FULL PASS. `campaign_history()`는 case ID 혼합 여부를 별도로 검증하지만, `validate_events(events,case_id=None)`는 각 이벤트의 schema/hash/seq만 확인한다. `case_ledger.py validate --ledger`에서는 `--case-id`가 선택 사항이라, 서로 다른 case ID를 가진 unsigned events와 재계산된 anchor를 정상으로 판정할 수 있었다.

수정: 명시적 case ID가 없으면 첫 유효 이벤트에서 ID를 추론하고 이후 모든 이벤트의 ID가 동일한지 검증. hash-chain과 anchor가 자체 일관성을 지녀도 타 case ID 혼입은 차단한다. CLI를 실제 호출해 실패 branch/message를 검증하는 회귀 테스트 추가.

### 57. 인증 witness가 손상돼도 anchor 검증이 이를 무시함

기존 `validate_anchor()`가 `load_auth_witness()`의 `ValueError`를 `witness=None`으로 무시했다. witness digest가 손상되어도 정상 anchor만 있으면 검증이 통과할 수 있다.

수정: existing witness의 schema, digest, case ID 불일치를 오류로 반환. signed/unsigned 정상 anchor를 각각 준비해 witness digest만 훼손했을 때 거부하고, 원본 witness로 되돌리면 정상 검증되는지 회귀 테스트 추가. 유효한 JSON이지만 event object가 아닌 입력이나 잘못된 anchor object는 예외 대신 검증 오류로 처리한다.

범위: Leonardo 검토 기준으로 정적 반례를 도출하고 CI에 실행 가능한 회귀를 추가한다. 별도 Leonardo 런타임 에이전트 호출은 불가하여 독립 실행 검토로 주장하지 않는다. 오직 이 두 무결성 결함과 입력 분류 회귀만 한 번에 보완하며 자동 ENFORCED 승격은 하지 않는다.

### 58. 심볼릭 링크 및 경로 리디렉션을 이용한 외부 ledger 기록 경계

HEAD `ca71139661783b1f52f8a3815b48ae7dea9e184c`에서 신규 `case-events.jsonl`이 dangling symbolic link일 때 `Path.exists()==False`여서 새 ledger로 오인할 수 있다. 그러나 뒤의 `Path.open('a')`는 링크 대상 경로를 따라 외부 파일을 새로 만들고 JSONL을 기록한다. 기존 부모 디렉터리나 anchor/journal 경로가 링크로 전환된 경우에도 파일 입출력은 원래 예상한 작업 공간을 벗어날 수 있다.

대응: append/recovery/anchor 경로의 기존 symlink, Windows junction, 상위 디렉터리 리디렉션 및 경로 traversal을 작업 파일 생성 전 검사한다. mutation 과정에서는 ledger lock을 취득한 후 다시 검사한다. dangling ledger 링크, redirected anchor, linked parent, linked pending journal의 2개 묶음 회귀 테스트를 추가한다. 외부 파일의 바이트/생성 상태가 유지되는지와 링크 제거 후 정상 복구를 확인한다.

범위: 이 preflight는 정적 경로 보호이며 race-free OS 샌드박스와 동일하지 않다. 경로를 공격자가 동시에 바꾸는 TOCTOU 위협의 완전 차단은 NOT_RUN/NOT_CLAIMED로 유지한다.

### 59. Python의 non-finite JSON 직렬화로 비표준 감사 이벤트가 기록됨

`common.canonical_bytes()` 및 `case_ledger._events_bytes()`는 기본 `json.dumps(allow_nan=True)`를 사용한다. `payload: {'value': float('nan')}`는 표면적 schema(object) 검증과 `object_digest()` 단계를 통과할 수 있어 `NaN` 문자열이 들어 있는 비표준 JSONL과 pending journal이 영속화된다. 다른 엄격 JSON 구현에서 파싱이 실패해 검증·감사 결과가 런타임마다 달라질 위험이 있다.

대응: 신규 이벤트는 `allow_nan=False`로 사전 직렬화 검사하고, ledger/anchor/witness/journal/CLI 입력은 non-finite constant 및 overflow 숫자를 거부하는 parser를 사용한다. 잘못된 journal dict/array는 내용 검증 전에 fail-closed 처리한다. 회귀: NaN/Infinity/-Infinity 신규/기존 ledger 거부, 비표준 pending 데이터 무변경 거부 후 정상 복구, overflow exponent 파싱 거부, non-object transaction typed rejection.

범위: Leonardo 검토 방식의 코드 분석과 실제 Python 직렬화 반례, GitHub 테스트 실행을 결합했다. 별도 Leonardo 런타임/독립 모델 세션 실행으로 해석하지 않는다. 신규 코드 HEAD CI 통과 전까지는 PASS로 표시하지 않는다.

### 60. 고정 임시 파일 이름의 symlink가 외부 파일을 truncate

기준 HEAD `9787a194713cbb0d6983f43df22821a211f14150` (Actions #792 PASS). 58번에서는 최종 ledger/anchor/journal/witness 경로의 링크를 차단했으나, `_atomic_json_fsync`와 `write_anchor`는 `<target>.tmp`를 고정 이름으로 `wb` 모드로 열었다. 별도로 심어 놓은 `<target>.tmp` 링크는 최종 경로 preflight에 포함되지 않았고 외부 파일의 원본 바이트가 교체 이전에 손상될 수 있었다. Python 파일 열기·symlink 반례로 재현.

대응: journal/anchor/auth witness atomic writer에 same-directory `tempfile.mkstemp` 사용 (O_EXCL·0600·fsync·os.replace); anchor JSON 키 출력 순서 유지. 구 고정 `.tmp` 링크나 일반 파일은 손대지 않음. 신규 회귀 2개에서 3개 writer의 링크 우회 및 기존 파일 보존 확인. 동시 경로 교체 TOCTOU는 여전히 외부 샌드박스 과제.

### 61. 서명된 JSON 객체의 중복 키를 통한 파서 불일치

`json.loads`는 같은 객체에 `"case_id": "ATTACKER"`와 `"case_id": "CASE"`가 있으면 마지막 값을 사용한다. 서명된 anchor 및 pending transaction에 먼저 중복 필드를 삽입하면 Python이 재구성하는 객체는 기존과 동일하므로 HMAC 검증이 통과할 수 있지만, 외부 파서는 첫 키나 중복 오류를 사용해 해석이 달라질 수 있다.

대응: `_strict_json_loads`에 object_pairs_hook 기반 중복 키 차단. 중첩 payload를 포함해 전체 신뢰 경로에서 파싱 단계에서 실패하며, 테스트는 signed anchor/transaction, auth witness, 중첩 ledger 이벤트 등 4개 신규 회귀로 구성. 에이전트 직접 실행은 불가했고 Leonardo 방식의 코드 경로 시뮬레이션·로컬 Python 반례 및 CI 테스트를 사용한다. 새 HEAD full/ZIP 검증 전엔 PASS 주장하지 않음.
