# v2.2 → v2.3 Migration

v2.2 evidence/review/case schema는 그대로 유지된다. v2.3은 이를 깨지 않고 orchestration contract를 추가한다.

1. 기존 v2.2 package 위에 v2.3을 배포한다.
2. `policy/reviewer-routing.yml`에서 실제 local L1/L2 identity를 설정한다.
3. 각 node에 reviewer worker wrapper를 배치한다.
4. 최초에는 `mode: shadow` 유지.
5. v2.2 `textdiff_adapter.py` 출력은 그대로 v2.3 `run_review_cycle.py` 입력으로 사용할 수 있다.
6. 새 case부터 `case-events.jsonl`을 함께 보관한다.
7. 기존 case-bank는 그대로 calibration 입력으로 사용할 수 있으나, v2.3 이전 case에는 event ledger가 없다는 것을 provenance에서 구분한다.


## Closeout 보완
- 커스텀 `reviewer-routing.yml`을 사용하는 노드는 v2.3 closeout 이후 생성되는 `policy_digest`가 이전 초안과 달라질 수 있다. 이는 실제 적용 정책을 provenance에 포함하기 위한 의도된 변경이다.
- `BLOCKED` reviewer 결과는 이제 cycle `BLOCKED`로 materialize된다. 기존 백데이터가 있다면 완료 상태와 혼동되지 않도록 재분류를 권장한다.
