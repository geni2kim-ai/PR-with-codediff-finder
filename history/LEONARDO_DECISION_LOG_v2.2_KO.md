# Leonardo 판단 기록 — Review Harness v2.2

## 입력

- 기존 `GitHub_PR_Review_Harness_v2.1`
- 제공받은 `TextDiffChecker_v1_4_6.zip`
- v1.4.6 × v2.1 통합 검토에서 발견된 H1~H5 / M1~M5
- 합의된 L1 → L2 → Adversarial → Human → Leonardo/Davinchi backdata 구조

## Leonardo 판정

다음 단계는 문서 추가가 아니라 **실행 경로를 닫는 구현**이어야 한다고 판단했다.

### 실제 재현된 핵심 반례

반복행/이동/대량수정 3,000행 fixture에서 v1.4.6 기본 모드는 `approx=False`이면서 edit cost 3472, extended full Myers는 2600이었다. 변환 자체는 유효하지만 전역 정렬 품질을 `approx` boolean만으로 표현하면 downstream reviewer가 과신할 수 있다.

### 조치

- 기존 GUI/API 호환은 유지.
- Harness 전용 `diff_texts_with_trace()` 추가.
- 기본 banded 경로를 `HEURISTIC`, extended full Myers 성공을 `PROVEN_EXACT`로 구분.
- 해당 반례를 자동 regression fixture로 고정.
- 실제 Git object를 읽는 adapter 구현.
- evidence/score/trail의 semantic binding 구현.
- reviewer provenance와 independent-context 조건 구현.
- Case Bank/Adversarial queue 자동 라우팅 구현.

## 추가 Leonardo 점검에서 발견한 항목

`output_digest`에 elapsed time을 포함하면 같은 의미의 재실행도 digest가 달라져 dedup/stability 분석이 어려웠다. 따라서:

- `semantic_digest`: performance telemetry 제외, 의미 동일성/dedup용
- `output_digest`: 전체 실행 evidence 무결성용

으로 분리했다.

또한 ADDED/DELETED 파일의 존재하지 않는 side를 빈 UTF-8 파일처럼 기록하던 adapter 설계 가능성을 차단하여, 없는 side의 encoding은 `null`로 기록하도록 했다.

## 현재 검증 결과

- TextDiff Harness build: 144 tests PASS, GUI class 1 skip.
- Harness: 23 unit/integration tests PASS.
- DIFF-FALSE-EXACT fixture: default 3472 / exact 2600 재현, quality class 구분 PASS.
- Git adapter smoke: protected path, test skip weakening, added-side encoding binding PASS.
- Git metadata manual probe: binary / generated / vendor / symlink / mode change 처리 PASS.
- schema + semantic validation examples PASS.

## NOT_RUN / 외부 연결 필요

- Windows 실제 GUI E2E / PyInstaller EXE 실행
- 대규모 실제 저장소 장시간 성능 benchmark
- 실제 L1/L2/Adversarial 모델 호출 오케스트레이션
- GitHub App/Actions Check Run 게시, CODEOWNERS 승인 조회, merge blocking API 연동
- post-merge incident source connector 자동 수집

이 항목들은 v2.2의 계약/입력·출력 구조는 마련되어 있으나, 해당 실행 환경의 인증·API·노드 구성에 맞춰 연결해야 한다.

## 승격 권고

현재 v2.2는 **local shadow/advisory deployment candidate**로 적합하다. 실제 저장소에서 backdata를 축적하면서 sensor quality class별 오류율, L1/L2 뒤집힘, adversarial overturn rate를 측정한 뒤 merge-blocking을 단계적으로 활성화한다.
