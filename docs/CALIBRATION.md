# Reviewer Calibration v2.7

Calibration은 lower reviewer를 **최종 기록과 비교**하되, 서로 다른 verdict vocabulary를 억지로 같은 값으로 취급하지 않는다.

## Machine-review agreement

L1/L2/ADVERSARIAL 비교는 raw `PASS/FINDINGS` 문자열이 아니라 **material state**를 사용한다.

- material finding 0개 + NOTE_ONLY만 존재 → `PASS`
- material finding 1개 이상 → `FINDINGS`
- reviewer BLOCKED → `BLOCKED`

따라서 L1이 오타 하나를 `FINDINGS`로 보고하고 L2가 `PASS`해도 material state가 동일하면 disagreement/reversal로 세지 않는다.

## HUMAN semantics

HUMAN은 `CONFIRMED/REJECTED` vocabulary를 사용하므로 machine reviewer의 `PASS/FINDINGS`와 직접 agreement 비교하지 않는다.

대신:
- `CONFIRMED` → parent review confirmation
- `REJECTED` → parent review rejection

으로 별도 집계한다. HUMAN 판단은 authority이지만, 문자열이 다르다는 이유로 L1/L2 accuracy를 0으로 만드는 방식은 사용하지 않는다.

## Sampling strata

Cases are split into at least:
- `random_audit`: unbiased sampling signal;
- `policy_escalation`: harder cases selected by risk/disagreement/novelty.

이 구분은 escalation-heavy case bank를 자연 모집단으로 오인하는 것을 방지한다.

## Leonardo metrics

v2.7 calibration은 다음을 직접 산출한다.

- `note_only_rate`
- `major_l2_downgrade_rate`
- `automated_attempts_p95`
- `same_material_repeat_rate`
- `review_budget_human_escalation_rate`
- recurring NOTE key/family occurrence

반복 NOTE의 기본 후보 threshold는 `policy/limits.yml`의 `recurring_note_min_occurrences`이며 현재 3 cases다.

반복 NOTE는 **standard/check proposal signal**일 뿐 authority가 아니다. 자동 수정/자동 standard 변경을 하지 않으며 Leonardo standard evolution의 재현→상위 adjudication→proposal→HUMAN/CODEOWNER 흐름을 유지한다.

Invalid JSON, missing ledgers, anchor mismatches and unavailable HMAC keys for HMAC-protected cases are surfaced in `invalid_or_unanchored_cases`; they are never silently skipped.

## Interpretation limit

현재 case-bank의 final case record는 campaign summary를 보존하지만, 이전 remediation attempt의 모든 모델/provenance trail을 하나의 case record에 재봉인하지는 않는다. 따라서 campaign-level 반복/시간 지표는 계산 가능하지만, 이전 attempt의 세부 model-by-model calibration 완전성은 별도 개선 후보로 남는다.
