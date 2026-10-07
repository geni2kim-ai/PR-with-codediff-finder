# Local Node Handoff — Review Harness v2.7

## 배포 모드

초기 배포는 반드시 `SHADOW`로 유지한다. 로컬 개발 노드의 코드 변경을 관측하면서 L1/L2/Adversarial 결과와 실제 수정 결과를 Case Bank에 축적한다.

## 기본 흐름

1. 작업 시작 또는 재개 직전에 trusted base ref와 **최신 committed HEAD**를 다시 확인한다.
2. 이전 리뷰/인계/PASS 결과가 있더라도 현재 HEAD와 다르면 STALE로 취급한다.
3. 개발 노드가 bounded 변경을 commit한다.
4. TextDiff evidence를 최신 HEAD에서 생성한다.
5. L1 리뷰를 수행한다.
6. 정책/신뢰도/위험/무작위 감사에 따라 L2를 수행한다.
7. disagreement/novel/security/governance/sensor conflict는 Adversarial로 보낸다.
8. Human-required 항목은 외부 서명 HUMAN authority로 마감한다.
9. 수정이 발생하면 **수정 후 최신 HEAD를 다시 리뷰하고 canonical validation을 재실행**한다.
10. outcome/post-merge 결과를 backdata에 기록한다.

## v2.7 추가 주의점

- HEAD가 그대로여도 base ref가 리뷰 중 움직이면 cycle은 `STALE`이다.
- standards/spec/tests와 effective policy는 cycle 시작 시 동결된 snapshot을 사용한다.
- HUMAN attestation freshness는 신규 승인 시점의 acceptance window다. ledger에 확정된 역사적 proof의 검증과 혼동하지 않는다.
- pending HUMAN/ledger recovery transaction을 임의 편집하지 않는다. digest/HMAC/binding 검증에 실패하면 자동 우회하지 말고 quarantine한다.
- 죽은 ledger lock은 owner PID 확인 후 회수되지만 살아 있는 owner의 lock은 강제로 제거하지 않는다.
- 기존 case-bank의 동일 case ID를 현재 case와 동일하다고 가정하지 않는다.
- reviewer task의 `worker_command_digest`를 보존하여 노드별 reviewer implementation 변화를 추적한다.
- ENFORCED는 외부 replay cache와 attestation issuer/key를 저장소 바깥 trust boundary로 운영한다.
- secret-like 환경변수 이름을 reviewer environment allowlist에 추가하지 않는다.

## 검증

```bash
python tools/run_validation.py --full --test-timeout 120
```

작업을 마감할 때는 동일한 최신 HEAD에서 MANIFEST와 CI 결과가 일치하는지 확인한다.

## ENFORCED 전환 전 필수

- OS sandbox E2E;
- external attestation issuer/key protection;
- 실제 L1/L2/Adversarial worker + fresh session 검증;
- GitHub required check / ruleset E2E;
- 충분한 random-audit calibration;
- 상위 reviewer/Human escalation 운영 절차.
