# Migration v2.6 → v2.7

## 운영상 변경점

1. 코드리뷰는 항상 대상 branch/PR의 **최신 committed HEAD**를 다시 조회한 뒤 시작하거나 재개한다.
2. HEAD/base/effective policy/manifest/standards/spec/tests가 바뀌면 이전 closeout은 최신 HEAD 재검토 전까지 STALE로 취급한다.
3. HUMAN attestation의 시간 제한은 신규 결정을 수락할 때 적용한다. 이미 ledger에 확정된 과거 HUMAN proof는 HMAC/binding으로 검증하며 단순 시간 경과로 무효화하지 않는다.
4. HUMAN recovery transaction은 digest와 HUMAN authority-key HMAC을 모두 검증한다.
5. ledger append 도중 프로세스가 종료될 경우 `*.append-transaction.json` recovery journal을 사용하여 정확히 중단된 append만 복구한다.
6. ledger lock의 owner PID가 종료된 경우 즉시 stale lock을 회수한다.
7. existing case-bank 재사용은 동일 case_id만으로 허용하지 않는다. case record, binding, sensor evidence digest가 immutable snapshot과 일치해야 한다.
8. standards/spec/test는 reviewer 실행 전에 case output의 `trusted-inputs/`로 동결된다.
9. review cycle은 `effective-policy/` snapshot만 사용하며 live policy 파일 재읽기에 의존하지 않는다.
10. 새 v2.7 runtime/human/ledger integrity artifact는 v2.7 marker를 생성한다. 필요한 v2.6 artifact 읽기 호환은 유지한다.

## 전환 절차

- 검증 완료된 v2.6 HEAD를 보존한다.
- `hardening/v2.7`을 v2.6 검증 HEAD에서 분기한다.
- v2.7 변경을 반영한 뒤 최신 HEAD를 다시 코드리뷰한다.
- `python tools/run_validation.py --full --test-timeout 120`을 최신 HEAD에서 수행한다.
- 동일 HEAD의 generated manifest와 committed `MANIFEST.sha256`을 일치시킨다.
- PR CI와 push CI가 모두 최신 HEAD에서 PASS한 뒤 review/evidence 문서를 고정한다.
- 외부 promotion gates가 실제로 검증되기 전에는 SHADOW 유지.
