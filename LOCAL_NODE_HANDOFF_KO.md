# Local Node Handoff — Review Harness v2.5

## 배포 모드
초기 배포는 반드시 `SHADOW`로 유지한다. 로컬 개발 노드의 코드 변경을 관측하면서 L1/L2/Adversarial 결과와 실제 수정 결과를 Case Bank에 축적한다.

## 기본 흐름
1. 작업 시작 전 trusted base ref와 현재 HEAD 확인.
2. 개발 노드가 bounded 변경을 commit.
3. TextDiff evidence 생성.
4. L1 리뷰.
5. 정책/신뢰도/위험/무작위 감사에 따라 L2.
6. disagreement/novel/security/governance/sensor conflict는 Adversarial.
7. Human-required 항목은 사용자 상위 모델 cross-check와 owner 판단으로 마감.
8. outcome/post-merge 결과를 backdata에 기록.

## v2.5 추가 주의점
- HEAD가 그대로여도 base ref가 리뷰 중 움직이면 cycle은 `STALE`이다.
- reviewer task의 `worker_command_digest`를 보존하여 노드별 reviewer implementation 변화를 추적한다.
- `MAESTRO_REVIEW_SANDBOX_VERIFIED=1`은 외부 runtime attestation이 검증된 ENFORCED에서만 의미가 있다.
- ENFORCED는 `MAESTRO_RUNTIME_ATTESTATION_REPLAY_DIR`을 저장소 바깥 launcher 소유 경로로 설정해야 하며 reviewer가 해당 cache를 삭제/수정할 수 없어야 한다. 한 번 소비된 nonce는 재사용할 수 없다.
- secret-like 환경변수 이름을 `environment_allowlist`에 추가하지 않는다.

## 검증
```bash
python tools/run_validation.py --full
```
장시간 CI/제약 환경에서는 `VALIDATION_COMMANDS.md`의 segmented commands를 사용한다.

## ENFORCED 전환 전 필수
- OS sandbox E2E;
- external attestation issuer/key protection;
- 실제 L1/L2/Adversarial worker + fresh session 검증;
- GitHub required check / ruleset E2E;
- 충분한 random-audit calibration;
- 상위 reviewer/Human escalation 운영 절차.
