# Validation Report — GitHub PR Review Harness v2.2

## 실행 결과

- Harness unit/integration: **23 PASS**
- TextDiffChecker harness build: **144 PASS, 1 GUI class skip**
- `DIFF-FALSE-EXACT` fixture: **PASS**
  - default edit cost: `3472`, quality: `HEURISTIC`
  - extended full Myers edit cost: `2600`, quality: `PROVEN_EXACT`
- TextDiff evidence schema + semantic validation: **PASS**
- Case record schema + semantic validation: **PASS**
- RSI evaluation score/promotion validation: **PASS**
- Review-result semantic validation: **PASS**
- Python compileall: **PASS**
- Git metadata manual probe: binary/generated/vendor/symlink/mode-change: **PASS**

## 주요 SHA-256

- Original TextDiffChecker v1.4.6 ZIP: `8f305c8bb4a0e192d9cac0bc8dc79f04fde5772adabda81158bc6b29cd4872a9`
- Harness patched `checker.py`: `62d6065855c8616a8c0273fdf75f24b186bad28a13d72794aff71b10f3ddcb06`
- `syntax_db.json`: `1672a0bf71531e076a04f493dfa117b8df53bc07ee29268ba30abd27e35bddcf`
- `protected-paths.yml`: `55a5ba1ce1161d1ac3d1db9fb4832d33b9cc4f437c08bebe74c269670490810f`
- `sensor-policy.yml`: `95d6985feb4cf9fc6a2fe49e321caa545c6fc8197e5a13549c06730f43721573`
- `rsi-scoring.yml`: `1da77fe1795eab0cc9d6f3bf0afe9445507f48f9c8fe7a7a023ac6c96f7f00aa`

## 검증되지 않은 범위

- Windows GUI 실제 조작 및 PyInstaller EXE 실행
- 실제 GitHub App/Actions Check Run 게시/merge-blocking API
- 실제 L1/L2/Adversarial 모델 호출 오케스트레이션
- 대형 실저장소 장시간 성능/비용 benchmark
- post-merge incident connector 자동 수집

현재 권장 배포 단계는 **local shadow/advisory**이며, 실제 backdata로 precision/recall과 계층별 overturn rate를 확인한 뒤 merge-blocking을 승격한다.
