# Harness integration patch notes

기준 제품 소스: TextDiffChecker v1.4.6
Harness API identity: `1.4.6-harness.1`

제품의 기존 `diff_texts()` 및 `diff_texts_with_opcodes()` 반환 계약은 변경하지 않았다.

추가 사항:
- `decode_text_bytes()` — Git blob을 파일 생성 없이 동일 디코딩 정책으로 처리.
- `diff_texts_with_trace()` — findings/stats/opcodes에 algorithm provenance 추가.
- `quality_class`: `PROVEN_EXACT | HEURISTIC | APPROXIMATE`.
- full Myers cap 초과 후 banded/patience 경로를 `HEURISTIC`으로 보수적으로 표시.
- `DIFF-FALSE-EXACT` 회귀 테스트 1건 + small SequenceMatcher quality 테스트 1건.

이 패치는 GUI 제품 버전을 임의로 1.4.7로 올리지 않는다. 제품 버전은 1.4.6으로 보존하고 Harness 통합 identity를 별도로 기록한다.
