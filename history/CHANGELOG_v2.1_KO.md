# v2.1 변경 요약

v2 피드백과 후속 합의를 반영한 주요 변경:

- Native Copilot과 외부 Harness 프로파일 분리
- TextDiffChecker를 `Local Coding Telemetry / Evidence Sensor`로 공식화
- L1 → L2 → ADVERSARIAL → HUMAN Review Authority Ladder 추가
- L1/L2/상위 판정 overwrite 금지 및 trail 보존
- adversarial queue 6종 분리 및 machine packet schema 추가
- 실제 coding/review/outcome/post-merge 결과를 backdata case record로 축적
- protected paths를 단일 YAML로 통합하고 `.github/**` blanket floor 제거
- PASS+상위검증 미완료는 gate `action_required`
- PASS+blocker/major, HARD+human=false, governance+non-HUMAN 등 schema/semantic 반례 차단
- risk floor와 reviewer level을 harness가 재계산
- spec provenance와 PR-open 이후 변경 경고 규격 추가
- output exfiltration 방지: external URL/image/@mention/secret-scan 규칙
- deterministic check를 구조화 (`passed|failed|unknown|not_required`)
- TextDiff RSI score vector, low-score case bank, failure-family, regression promotion 규칙 추가
- benchmark 반복 안정성(N>=5), 모델/설정 pinning, 운영 기반 diff size calibration 절차 추가
- RSI/Davinchi는 proposal-only; standards/policy self-update/self-approval 금지
