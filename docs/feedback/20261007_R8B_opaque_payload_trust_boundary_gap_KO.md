# CodeDiff 피드백 — R8B nested authority-field / payload interpretation gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R8B mediated boundary review
- 분류: `SEMANTIC_REVIEW_GAP / FALSE_NEGATIVE_RISK`
- 상태: `OPEN → LOCAL REMEDIATION PREPARED`

## 관찰

R8B policy는 child message에 `node_id`, `token`, `grant` 같은 authority 관련 key가 있는지 검사하지만,
현재 검사는 message 최상위 key에만 적용된다.

향후 child output을 JSON/object로 직접 해석하는 구현이 붙으면 nested object 안의 authority-like field를
놓칠 수 있다.

예를 들어 top-level에는 금지 key가 없지만 하위 object에 동일 의미의 key가 있을 수 있다.

## 영향

- 현재 R8B는 design/prep only라 live authority 영향은 없다.
- 하지만 child-provided structured data를 신뢰 경계 안쪽에서 재해석하면 self-asserted identity/authority가
  downstream logic에 섞일 위험이 있다.
- CodeDiff routing은 높은 검토 단계로 올렸지만 이 semantic trust-boundary gap을 직접 발견하지 못했다.

## 권고

더 단순하고 강한 규칙은 **opaque payload mediation**이다.

- child output을 identity-bearing JSON으로 신뢰하지 않는다.
- mediator가 raw payload bytes를 수신한다.
- mediator가 직접 message id, sequence, child process binding, payload SHA-256, trust label을 만든다.
- child payload 내부 field는 authority decision에 사용하지 않는다.
- structured parsing이 필요한 경우 별도 untrusted-content parser 뒤에서만 수행한다.

따라서 authority-field denylist는 방어층으로 남길 수 있지만, 핵심 신뢰 모델은 field filtering이 아니라
`opaque bytes + mediator-generated provenance`가 되어야 한다.

## CodeDiff 관점

이번 finding은 syntax/path diff 문제가 아니라 **data interpretation trust boundary** 문제다.
direct semantic review와 routing 성능을 별도로 측정해야 하는 또 하나의 사례다.
