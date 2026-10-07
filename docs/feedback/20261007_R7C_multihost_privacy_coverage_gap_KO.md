# CodeDiff 실사용 피드백 — multi-host privacy coverage gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R7C controlled-launcher discovery preparation
- 분류: `EVIDENCE_GAP / PRIVACY_FALSE_NEGATIVE_RISK`
- 상태: `OPEN → LOCAL MITIGATION PREPARED`
- authority effect: `NONE`

## 관찰

현재 privacy scanner는 packaging host의 계정명, 컴퓨터명, profile/temp 경로와 optional local-only patterns를
기준으로 distributable raw bytes를 검사한다.

이 방식은 evidence 생성 host와 sealing host가 같을 때는 적절하지만, 여러 노드의 evidence를 한 노드에서
합치는 경우 다른 source host의 identifier를 자동으로 알 수 없다.

따라서 multi-host package에서 current-host pattern만 사용하면 source-host identifier 누출을 놓칠 수 있다.

## 영향

- privacy seal PASS가 multi-host 전체 privacy completeness를 의미하지 않을 수 있다.
- integrity lineage가 정확해도 privacy source coverage는 불완전할 수 있다.

## 권고

각 source host마다 local-only privacy pattern material을 생성하고, sealing 단계가 이를 함께 받아 scan해야 한다.

최종 distributable에는 literal pattern을 넣지 않고 다음만 기록한다.

- source evidence ID
- pattern class
- pattern commitment hash/length
- source pattern set count
- scan encoding
- match count
- coverage status

source evidence가 존재하지만 해당 host의 privacy pattern material이 없으면:

`PRIVACY_SOURCE_COVERAGE_INCOMPLETE`

로 sealing을 막는 것이 안전하다.

## CodeDiff/evidence packaging 관점

공통 package seal은 다음을 별도 gate로 관리하는 것이 좋다.

- source/code lineage
- evidence integrity lineage
- privacy transform lineage
- privacy source coverage

## 로컬 보완

R7C package helper는 current-host patterns뿐 아니라 local-only imported source pattern sets와 source evidence ID를
함께 받아 scan하도록 확장한다.

distributable report에는 literal identifier가 아니라 commitments와 coverage summary만 남긴다.

## 결론

current-host privacy scan PASS를 multi-host evidence 전체 privacy PASS로 확대 해석하면 안 된다.
