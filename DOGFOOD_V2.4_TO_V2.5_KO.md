# v2.4 → v2.5 Dogfood Review 기록

## 원칙
후보 v2.5가 자기 자신을 승인하지 않도록 **v2.4를 고정된 SHADOW reviewer baseline**으로 사용했다.

## Batch 1
- 대상: temporal trust hardening 초안
- v2.4 sensor: `HEURISTIC`, `trusted_for_gate=true`
- 보호 경로: `policy/reviewer-routing.yml`, `schemas/reviewer-task.schema.json`
- v2.4 cycle: `HUMAN_REQUIRED`
- required: `HUMAN`
- achieved: `ADVERSARIAL`
- gate: `action_required`
- 의미: reviewer 정책/스키마 자체 변경을 자동 승인하지 않는 governance floor가 실제 동작함.

## Batch 2
- 대상: reviewer worker provenance + env boundary
- v2.4 sensor: `HEURISTIC`, `trusted_for_gate=true`
- 변경 파일: 12
- 보호 경로: routing policy + reviewer/case schema
- v2.4 cycle: `HUMAN_REQUIRED`
- required: `HUMAN`
- achieved: `ADVERSARIAL`
- gate: `action_required`

## 개발 과정에서 잡힌 실제 회귀
1. 테스트 파일의 `unittest.main()` 위치 때문에 파일 직접 실행 시 뒤쪽 테스트 클래스가 누락될 수 있던 문제 → 수정.
2. `RUNTIME_ATTESTED` ledger event를 구현했으나 event schema enum을 갱신하지 않아 ENFORCED 정상 경로가 차단되는 문제 → 신규 회귀 테스트가 발견, 수정.
3. 기존 validation runner의 thread/subprocess/multiprocessing 조합이 일부 POSIX 환경에서 불안정할 수 있는 문제 → process-group + file-backed output 방식으로 재구성.

## 판정
Dogfood는 “candidate 자체 테스트 PASS”와 “기존 안정판의 권한 판정”을 분리하는 데 효과가 있었다. v2.5도 SHADOW 배포 후보이며, v2.5 자신이 v2.5를 최종 승인한 것으로 취급하지 않는다.

## Final clean-tree review after validation-isolation and bytecode hardening
- stable reviewer package: **v2.4**
- reviewed candidate code commit: `864ef63404f3b9997ce123a661afdf0a8056efc8`
- comparison: `37846aa` (v2.4 base) ... reviewed candidate HEAD
- execution: stable v2.4 TextDiff adapter + stable v2.4 SHADOW cycle
- review workers: stable package의 deterministic `mock_reviewer --mode pass`를 사용해 **authority routing / policy floor**를 검증함. 이는 실제 상위 모델의 의미론적 코드 승인으로 간주하지 않는다.
- changed files: **25**
- changed lines: **1006**
- TextDiff quality: `HEURISTIC`
- sensor trust: `trusted_for_gate=true`
- weakening signals: 없음
- protected candidates:
  - `policy/reviewer-routing.yml`
  - `schemas/case-event.schema.json`
  - `schemas/case-record.schema.json`
  - `schemas/reviewer-stage-result.schema.json`
  - `schemas/reviewer-task.schema.json`
- final cycle: `HUMAN_REQUIRED`
- required level: `HUMAN`
- achieved level: `ADVERSARIAL`
- gate: `action_required`
- escalation reasons:
  - `ADVERSARIAL:adversarial_protected_path`
  - `ADVERSARIAL:governance_change`
  - `ADVERSARIAL:protected_path_adversarial_floor`
  - `HUMAN:governance_change`

### Dogfood에서 추가 발견된 자기오염
최종 stable cycle 첫 시도에서 review tooling 자체가 candidate repo에 `tools/__pycache__`를 생성해 `WORKTREE_DIRTY_*`로 차단되는 현상을 재현했다. v2.5에 `__pycache__/`, `*.py[cod]` ignore와 회귀 테스트를 추가한 뒤 동일 stable review를 재실행해 위 `HUMAN_REQUIRED` 결과를 얻었다.

### 해석
stable v2.4는 candidate의 policy/schema 자기 변경을 자동 승인하지 않고 Human authority까지 올렸다. v2.5 내부 테스트 PASS와 독립된 governance 결과다. 이 리뷰 이후 실행 코드 변경은 없고 closeout 보고/manifest/package metadata만 추가한다.
