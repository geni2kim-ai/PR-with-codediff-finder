# Migration v2.5 → v2.6

## 반드시 바뀌는 운영 항목
1. ledger anchor 경로는 `case-events.anchor.json`을 사용한다.
2. 기존 HMAC anchor가 있으면 동일 key 없이 append할 수 없다.
3. HUMAN_REQUIRED를 닫으려면 외부 서명 human attestation과 동일 HEAD가 필요하다.
4. `render_github_check.py`는 cycle 파일만으로 success를 만들지 않는다. 같은 case ledger/anchor가 필요하다.
5. ENFORCED에서 `--disable-random-audit`는 허용되지 않는다.
6. ENFORCED random audit에는 외부 `MAESTRO_AUDIT_SEED`가 필요하다.
7. L2/Adversarial fresh-session은 routing YAML 자기선언이 아니라 signed runtime attestation으로 전달하며, launcher가 `--l2-fresh-session --adversarial-fresh-session`을 명시하지 않으면 false로 처리한다.
8. harness 저장소 자체를 리뷰할 때 `tools/tests/vendor/requirements` 변경은 self-protection floor를 받는다.

## 권장 전환 절차
- v2.5를 stable SHADOW baseline으로 고정한다.
- v2.6 후보를 v2.5로 검토한다.
- 기존 Case Bank는 수정하지 않고 새 v2.6 case부터 canonical anchor 규칙을 적용한다.
- 외부 issuer/key와 GitHub required-check E2E가 준비되기 전에는 SHADOW 유지.
- v2.6이 독립 검토와 운영 calibration을 통과한 뒤에만 stable baseline을 v2.6으로 승격한다.
