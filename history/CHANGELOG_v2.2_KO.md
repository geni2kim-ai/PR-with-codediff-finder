# v2.2 변경 요약

## Leonardo 판단에 따른 P0 완료

1. `DIFF-FALSE-EXACT` 실제 반례를 regression fixture로 고정.
2. TextDiffChecker 기존 API를 유지하면서 Harness trace API 추가.
3. `PROVEN_EXACT / HEURISTIC / APPROXIMATE` quality class 도입.
4. executable `textdiff_adapter.py` 구현.
5. Git 파일별 base/head blob SHA, rename/copy/mode/symlink/submodule/binary/generated/vendor/encoding metadata 추가.
6. `output_digest`, summary, algorithm-quality, runtime trust semantic validator 구현.
7. `regex` timeout 미지원 runtime fail-closed.
8. RSI overall/promotion 재계산 validator 구현.
9. review trail provenance/independence semantic validator 구현.

## P1 완료

10. `evaluate_sensor_case.py` 자동 score 생성기 추가.
11. `route_case.py` Case Bank/adversarial queue 라우터 추가.
12. L1/L2/Adversarial model, prompt, skill, policy, standards, evidence digest provenance 추가.
13. encoding confidence를 evidence에 추가하고 review escalation signal로 연결.
14. 중앙 evidence에서 raw source/hunk 본문을 제외.
15. sensor quality/runtime 신호를 Review Authority Ladder floor에 연결.

## 검증

- TextDiffChecker Harness build: 기존 142 테스트 + 신규 2 regression = 144 PASS, GUI class 1 skip.
- Harness unit/integration: 23 PASS.
- 실제 임시 Git repo adapter smoke test PASS.
- v2.2 example schemas/semantic validators PASS.
