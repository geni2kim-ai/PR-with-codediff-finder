# v2.6 최신-HEAD 재검토 → v2.7 처리표

| # | 재검토에서 확인된 문제 | v2.7 처리 | 상태 |
|---|---|---|---|
| 1 | HUMAN attestation 5분 freshness가 과거 확정 proof 렌더링까지 막을 수 있음 | 신규 acceptance와 historical verification 분리 | 해결 |
| 2 | HUMAN recovery transaction이 unkeyed digest만으로 보호됨 | transaction digest + HUMAN authority-key HMAC + transaction-id 재계산 | 해결 |
| 3 | ledger event fsync 후 anchor replace 전 중단 시 다음 실행이 anchor 불일치로 막힐 수 있음 | authenticated append recovery journal + exact pre-ledger byte binding | 해결 |
| 4 | 프로세스 종료 후 ledger lock이 남으면 즉시 재시작이 timeout될 수 있음 | owner PID 생존 확인 후 dead lock 즉시 회수 | 해결 |
| 5 | 동일 case_id의 기존 case-bank가 현재 case와 다른데도 이전 packet을 재큐잉할 수 있음 | current case/binding/evidence와 immutable snapshot 일치 필수 | 해결 |
| 6 | standards/spec/test가 reviewer 실행 전에 바뀔 TOCTOU 가능성 | `trusted-inputs/` snapshot으로 동결 | 해결 |
| 7 | effective-policy를 만들고도 일부 판단/검증이 live policy를 다시 읽음 | routing/escalation/sensor recompute/evidence validation/reviewer provenance를 동일 snapshot에 고정 | 해결 |
| 8 | override sensor policy를 사용하면서 evidence `config_sha256`은 기본 live policy를 해시 | 실제 effective sensor policy bytes에 digest 바인딩 | 해결 |
| 9 | 작업 재개 시 이전 코드리뷰가 자동으로 현재 코드리뷰처럼 사용될 운영 위험 | repository `AGENTS.md` + Review Policy에 Latest-HEAD 규칙을 기본지침으로 고정 | 해결 |

## v2.7 검수 원칙

- 최신 committed HEAD를 먼저 조회한다.
- 수정 후에는 해당 patch만 보는 것이 아니라 최신 HEAD 전체 경계를 다시 검토한다.
- MANIFEST/CI/review report가 동일 HEAD를 가리켜야 한다.
- 이전 PASS는 newer HEAD에 승계되지 않는다.
- 외부 E2E가 NOT_RUN이면 이를 명시하고 ENFORCED/merge 권한으로 해석하지 않는다.
