# 로컬 노드 인계 지시서 — Review Harness v2.2

## 목적

각 로컬 개발 노드의 실제 코딩 결과를 자동으로 evidence화하고, L1/L2/Adversarial/Human 검증 결과를 backdata로 남겨 Leonardo/Davinchi 개선 루프에 사용한다.

## 배치 순서

1. `policy/`, `schemas/`, `profiles/harness/`를 PR이 임의로 바꿀 수 없는 trusted snapshot으로 제공한다.
2. Python 의존성을 설치한다: `pip install -r requirements.txt`.
3. 작업 단위마다 base/head SHA를 고정한다.
4. `tools/textdiff_adapter.py`로 evidence JSON을 생성한다.
5. `validate_textdiff_evidence.py`를 반드시 통과시킨다. 실패하면 reviewer에 trusted evidence로 전달하지 않는다.
6. L1은 evidence + trusted spec/standards만 받아 1차 검토한다.
7. Harness가 보호 경로, sensor quality/runtime, 위험도, 불일치 신호를 재계산해 최소 required level을 정한다.
8. L2는 필요한 건만 **독립 context**에서 재검토한다.
9. L1/L2 불일치, 신규 failure family, sensor/reviewer 충돌, 고위험·보안·거버넌스는 adversarial packet으로 분리한다.
10. 상위 모델/사람 결과는 기존 trail에 append한다. overwrite 금지.
11. author fix/reject, merge, post-merge incident를 case record에 연결한다.
12. `evaluate_sensor_case.py`로 사후 score를 생성하고 `validate_rsi_evaluation.py`로 재검증한다.
13. `route_case.py`가 Case Bank와 adversarial queue를 구성한다.
14. 반복/중대 실패는 regression fixture와 개선 후보 branch로 전환한다. 자기 승인 금지.

## TextDiff 품질 사용 규칙

- `PROVEN_EXACT`: 일반 evidence로 사용 가능.
- `HEURISTIC`: 일반 저위험에서는 사용 가능하나, auth/security/governance/human-floor와 결합하면 상위 검증을 요구한다.
- `APPROXIMATE`: 최소 L2 검토. 고위험이면 Adversarial 이상.
- `trusted_for_gate=false`: 최소 L2. 보호 경로와 결합하면 Adversarial 이상.
- failed invariant: Adversarial 검증 전까지 최종 성공 판정 금지.

## 로컬에서 보존할 데이터

`semantic_digest`를 같은 의미의 반복 실행/dedup 키로 사용하고 `output_digest`를 개별 실행 무결성 키로 사용한다.

원본 소스는 기존 저장소에 남긴다. 중앙 Case Bank에는 기본적으로 SHA/digest, 파일 특성, diff 품질, reviewer provenance, 결과/사후 상태만 보존한다. regression fixture가 필요하면 최소화·비식별화한 재현본을 별도로 만든다.
