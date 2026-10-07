# v2.5 Stable Baseline → v2.6 Candidate Dogfood

v2.6 후보는 자기 자신을 최종 승인자로 사용하지 않았다. 별도 v2.5 stable harness에서 현재 v2.6 후보 소스를 Git diff로 만들고 TextDiff → L1 → L2 → Adversarial 흐름을 SHADOW로 실행했다.

## 결과

- 변경 파일: **50**
- changed lines: **2,293**
- stable v2.5 sensor quality: **HEURISTIC**
- `trusted_for_gate`: **true**
- mock L1/L2/Adversarial verdict: 모두 PASS
- required authority: **HUMAN**
- achieved authority: **ADVERSARIAL**
- state: **HUMAN_REQUIRED**
- gate: **action_required**

즉 candidate 자체의 테스트 PASS나 reviewer PASS가 governance/HUMAN floor를 낮추지 못했다.

## 해석 범위

이 dogfood는 의미론적 코드 품질 승인이 아니다. reviewer는 mock PASS worker이므로 다음만 확인한다.

1. stable sensor가 candidate diff를 읽고 evidence에 바인딩한다.
2. 정책/테스트/도구 변경이 escalation signal로 남는다.
3. Adversarial까지 모두 PASS여도 HUMAN floor가 유지된다.
4. candidate가 자기 자신을 final approval authority로 사용하지 않는다.

원시 산출물은 `dogfood/v2.5-stable-v2.6-candidate/`에 있으며, `reviewed-snapshot.sha256`으로 당시 리뷰 대상 source bytes를 확인할 수 있다.
