# DIFF-FALSE-EXACT fixture

v1.4.6에서 `approx=False`였지만 기본 banded Myers 경로가 extended full Myers보다 비최적이었던 실제 반례를 최소한의 생성 코드로 고정한다.

v2.2에서는 기존 `approx` 호환 필드는 유지하되, Harness trace가 기본 경로를 `HEURISTIC`으로 표시해야 한다. `exact=True`에서 full Myers가 성공하는 동일 케이스는 `PROVEN_EXACT`이어야 한다.

실행:

```bash
python fixtures/diff-false-exact/fixture.py
```
