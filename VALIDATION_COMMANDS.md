# Validation Commands — v2.7

## Canonical full validation

```bash
python tools/run_validation.py --full
```

The runner automatically discovers `tests/test_*.py`. Multiprocessing/subprocess-sensitive v2.3 and v2.6 cases are isolated into independent test groups so a newly added test file cannot silently be omitted.

## Coverage check only

```bash
python - <<'PY'
import sys
sys.path.insert(0, 'tools')
import run_validation
errors = run_validation.validation_coverage_errors()
print(errors or 'PASS')
raise SystemExit(1 if errors else 0)
PY
```

## Segmented reproduction

```bash
python -m unittest -q tests.test_policy_engine
python -m unittest -q tests.test_v22_integration
python -m unittest -q tests.test_v24_hardening
python -m unittest -q tests.test_v25_dogfood
```

v2.3 and v2.6 subprocess-heavy regression tests should normally be run through the canonical runner. To inspect discovered groups:

```bash
python - <<'PY'
import sys
sys.path.insert(0, 'tools')
import run_validation
for group in run_validation.validation_groups():
    print(group)
PY
```

## Examples / schema semantics

```bash
python - <<'PY'
import sys
sys.path.insert(0, 'tools')
import run_validation
run_validation.validate_examples()
PY
```

## Vendored TextDiffChecker

```bash
python -m unittest discover -s vendor/TextDiffChecker_v1.4.6-harness.1/tests -q
python fixtures/diff-false-exact/fixture.py
```

## Static Python compilation

```bash
python -m compileall -q tools tests
```
