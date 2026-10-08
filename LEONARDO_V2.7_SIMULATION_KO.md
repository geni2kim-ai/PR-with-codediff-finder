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

