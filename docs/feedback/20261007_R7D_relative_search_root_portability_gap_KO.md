# CodeDiff 피드백 — R7D relative search-root portability gap

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R7D controlled source-root locator
- 분류: `FALSE_NEGATIVE_RISK / PORTABILITY_GAP`
- 상태: `OPEN → LOCAL FIX PREPARED`

## 관찰

R7D locator의 `scan()`은 각 search root를 내부에서 `resolve()`한 뒤, hit를 기록할 때
원래 `search_roots` 리스트에서 `index(resolved_root)`를 호출한다.

상대경로가 입력되면 원본 리스트에는 unresolved Path가 있고 내부 변수는 absolute resolved Path가 되므로,
동일한 root라도 `index()`가 실패할 수 있다.

YM 실행은 정규화된 bounded root를 사용해 정상 완료됐지만, 상대경로 사용 시 portability 문제가 생길 수 있다.

## 영향

- absolute path에서는 정상 동작할 수 있음
- relative path에서 hit가 발생하는 순간 예외가 날 수 있음
- no-hit run에서는 문제를 숨길 수 있어 테스트가 놓치기 쉬움

## 권고

root ID는 `list.index()`로 역조회하지 말고 입력을 normalize한 뒤 `enumerate()`로 직접 결합한다.

예:

```python
for root_index, raw_root in enumerate(search_roots, 1):
    root = raw_root.resolve()
    ...
    hit["search_root_id"] = str(root_index)
```

그리고 relative-root + actual fingerprint hit fixture를 regression test에 추가한다.

## CodeDiff 관점

이번 finding은 변경 범위/risk routing이 아니라 language/runtime semantics와 path normalization의 결합 문제다.
CodeDiff는 해당 변경을 높은 review 단계로 올렸지만 이 portability defect를 직접 발견하지 못했다.
