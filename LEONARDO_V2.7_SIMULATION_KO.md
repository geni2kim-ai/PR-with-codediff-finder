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

