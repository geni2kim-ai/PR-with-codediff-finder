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

