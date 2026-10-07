# Changelog v2.6

## 목적
v2.5 외부 adversarial review에서 재현된 authority/ledger/sensor/runtime 우회를 제거하고, 실제 로컬 코딩 리뷰 backdata를 더 신뢰할 수 있게 만든다.

## 주요 변경
- ledger anchor 이름 통일 및 기존 anchor 사전 검증
- HMAC anchor downgrade/delete-recreate 차단
- HUMAN floor를 cycle 단일 정책 경로에 강제
- harness self-protection + case-insensitive path policy
- HUMAN_CONFIRMED / HUMAN_REJECTED 전이와 signed human attestation
- GitHub check render 시 ledger `CYCLE_CLOSED` 대조
- Git exact path와 policy-normalized path 분리
- DETERMINISTIC quality class 추가
- weakening signal LF parsing 고정
- output URL/secret scan 재설계
- destructive migration / public contract / CODEOWNERS-ruleset / payment signal 생성
- worker timeout/process-tree hardening
- random audit 외부 seed 기반 재현성 + ENFORCED disable 금지
- worker command digest에 module source + cwd 바인딩
- Case Bank/queue immutable write와 packet standards/test refs 보존
- validation auto-discovery 및 v2.6 adversarial regressions

## 호환성
Harness release는 v2.6이지만 기존 reviewer/evidence JSON의 `schema_version: "2.4"` wire contract는 의도적으로 유지한다. `policy/reviewer-routing.yml`, runtime/human attestation처럼 v2.6 의미론이 필요한 구성은 별도 `2.6` 버전을 사용한다.
