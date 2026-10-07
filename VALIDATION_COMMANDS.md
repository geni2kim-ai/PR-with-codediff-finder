# Validation Commands — v2.5

## Canonical
```bash
python tools/run_validation.py --full
```

## Segmented reproduction
환경의 단일-command wall-clock 제한이 짧은 경우 아래를 분리 실행한다.

```bash
python -m unittest -q tests.test_policy_engine
python -m unittest -q tests.test_v22_integration
```

v2.3 orchestration은 상태 누적 영향을 피하기 위해 test method 단위 process isolation을 사용한다. v2.5 validation runner는 test enumeration 자체도 disposable subprocess에서 수행해 부모 validation process가 multiprocessing test module을 import하지 않는다.

```bash
python -m unittest -q tests.test_v24_hardening.PathAndGitEvidenceTests
python -m unittest -q tests.test_v24_hardening.TraceParityTests
python -m unittest -q tests.test_v24_hardening.RuntimeIntegrityTests
python -m unittest -q tests.test_v24_hardening.LedgerTests
python -m unittest -q tests.test_v24_hardening.PolicyAndProvenanceTests
python -m unittest -q tests.test_v25_dogfood
```

```bash
python - <<'PY'
import sys
sys.path.insert(0,'tools')
import run_validation
run_validation.validate_examples()
PY

python -m unittest discover -s vendor/TextDiffChecker_v1.4.6-harness.1/tests -q
python fixtures/diff-false-exact/fixture.py
```
