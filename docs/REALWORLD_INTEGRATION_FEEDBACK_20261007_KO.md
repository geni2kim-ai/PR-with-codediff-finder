# PR-with-codediff-finder v2.5 실사용 통합 피드백

- 대상 저장소: `geni2kim-ai/PR-with-codediff-finder`
- 기준 버전: `2.5`
- 기준 커밋: `69978ff50bc4003d6d73b8219790106846220f72`
- 적용 사례: Synapse agent boot authentication R6 → R6.1 → R6.2
- 검토 성격: 실제 코드 작업에 SHADOW sensor로 병행 적용한 결과
- 권한 효과: 없음. 본 문서는 피드백/개선 제안이며 승인 판정이 아님.

## 1. 요약

실제 보안 경계 코드를 수정하는 작업에 v2.5를 병행 적용한 결과, 이 도구의 가장 강한 장점은 **버그를 직접 고치는 것보다 변경 범위·위험 경로·검토 강도·lineage를 안정적으로 묶어주는 것**이었다.

특히 보안 관련 변경을 단순 테스트 PASS로 종료하지 않고 더 높은 검토 단계로 올리는 역할은 유용했다. 반면 현재 공개 v2.5 상태에서는 trusted TextDiff sensor를 완전히 재현하지 못해, 실사용 평가는 주로 degraded SHADOW 경로에 기반한다.

현재 실사용 판단:

- 변경 범위 추적: 강점
- protected-path / 위험도 escalation: 강점
- lineage / evidence packaging: 강점
- 테스트 약화 패턴 감시: 유용
- 의미론적 버그 직접 발견: degraded 모드에서는 제한적
- 단독 승인 도구: 부적합
- 상위 의미론 검토/적대적 검토와 병행: 적합

## 2. P1 — 공개 v2.5 trusted sensor 재현성 차단

### 관찰

`tools/textdiff_adapter.py`는 다음 asset을 신뢰 루트 일부로 요구한다.

`vendor/TextDiffChecker_v1_4_6_original.zip`

또한 `policy/sensor-policy.yml`에는 이 asset의 SHA-256이 고정돼 있다.

`8f305c8bb4a0e192d9cac0bc8dc79f04fde5772adabda81158bc6b29cd4872a9`

그러나 기준 커밋 `69978ff5...`의 공개 tree/manifest에서는 해당 ZIP을 확인하지 못했다.

### 영향

공개 저장소만 받은 외부 사용자는 exact trusted runtime을 재현할 수 없다. 결과적으로 공식 adapter 대신 별도 degraded 경로를 만들어야 했고, 해당 결과는 올바르게 `trusted_for_gate=false`로 취급했다.

### 권고

다음 중 하나를 권장한다.

1. 해당 original ZIP을 release asset 또는 별도 immutable artifact로 배포하고 SHA-256으로 검증 가능하게 한다.
2. 저장소에 넣지 않는다면 공식 bootstrap/materialize 명령을 제공해 pinned digest로 안전하게 가져오게 한다.
3. asset 미존재 시 adapter가 단순 실패하지 않고 명확한 typed 상태를 반환하게 한다.

예:

```text
TRUSTED_SENSOR_ASSET_UNAVAILABLE
sensor_mode=DEGRADED
trusted_for_gate=false
missing_asset=vendor/TextDiffChecker_v1_4_6_original.zip
expected_sha256=...
```

이 항목은 외부 재현성과 직접 연결되므로 P1로 본다.

## 3. P1/P2 — first-class degraded sensor 모드가 필요

### 관찰

실사용 중 trusted TextDiff runtime이 준비되지 않은 상태에서도 다음 정보는 충분히 유용했다.

- base/head SHA
- merge-base
- changed files
- changed lines
- rename/copy
- protected-path hit
- 테스트 약화 패턴
- required review level

이 경우 별도 bridge를 만들어 `DEGRADED_GIT_INVENTORY`로 운용했다.

### 문제

공식 trusted sensor와 fallback 결과 사이에 명확한 표준 모드가 없으면 외부 통합자가 자신이 만든 fallback을 공식 결과처럼 오해할 위험이 있다.

### 권고

공식 evidence schema에 다음 필드를 1급 개념으로 두는 것을 권장한다.

```json
{
  "sensor_mode": "TRUSTED_TEXTDIFF | DEGRADED_GIT_INVENTORY",
  "trusted_for_gate": false,
  "degradation_reasons": [],
  "coverage_gaps": [],
  "authority_effect": "NONE"
}
```

그리고 degraded 모드는 절대로 trusted TextDiff와 동등한 PASS를 주장하지 못하게 한다.

## 4. P2 — 프로젝트별 protected-path overlay 계약 필요

### 관찰

기본 정책은 `auth/**`, `security/**`, `crypto/**`처럼 일반적인 경로를 잘 다룬다.

그러나 실제 프로젝트에서는 보안 경계 코드가 다음처럼 존재할 수 있다.

```text
r6/**
r7/**
windows/R6NamedPipeCapture.cs
agent_runtime/**
broker/**
```

Synapse 적용에서는 별도 overlay를 두지 않으면 R6/R7 인증 경계를 기본 정책만으로 충분히 강하게 분류하기 어렵다.

### 권고

공식 CLI/API에 project overlay를 명시적으로 지원하면 좋다.

예:

```bash
python tools/textdiff_adapter.py \
  --policy policy/protected-paths.yml \
  --policy-overlay project/protected-paths.override.yml
```

추가로 최종 evidence에 다음을 기록하면 좋다.

- base policy SHA
- overlay policy SHA
- 적용 후 effective policy digest
- overlay가 올린 floor와 그 이유

## 5. P2 — usage/problem log 표준화 권고

실제 적용 과정에서 다음 종류의 문제가 발생했다.

- 실행환경 문제: 컨테이너 DNS로 `git clone` 실패
- upstream packaging 문제: pinned trusted asset 부재
- 프로젝트 taxonomy gap
- false-negative 가능성이 있는 의미론적 코드 문제
- host/runtime interaction
- evidence packaging 누락
- masking/provenance trade-off
- 로컬 통합자의 snapshot SHA 불일치

이런 문제를 코드 finding과 같은 통에 넣으면 원인 분석이 어렵다.

### 권고

도구 자체에 append-only usage log schema를 두는 것이 유용하다.

예:

```json
{
  "timestamp_utc": "...",
  "kind": "ENVIRONMENT_LIMITATION | TOOL_DEFECT | FALSE_POSITIVE | FALSE_NEGATIVE | INTEGRATION_GAP | PACKAGING_GAP",
  "severity": "low | medium | high",
  "source": "...",
  "summary": "...",
  "impact": "...",
  "remediation": "..."
}
```

그리고 review-cycle/package 생성 시 이 로그를 자동 포함하면 dogfood와 장기 성능 개선에 도움이 된다.

## 6. P2 — provenance self-check는 강점, 더 전면화할 가치가 있음

이번 통합에서 로컬로 복사한 `policy_engine.py`가 처음에는 pinned upstream SHA와 일치하지 않았다.

이 문제는 SHA 검증으로 즉시 드러났고, exact source로 복원한 뒤에야 snapshot으로 인정했다.

즉 **도구 자체가 강조하는 digest/lineage 원칙이 실제 통합 실수를 잡는 데 효과가 있었다.**

### 권고

외부 통합용으로 다음 명령을 제공하면 좋다.

```bash
python tools/verify_distribution.py --commit <sha>
```

검증 대상:

- core tools
- policy files
- schemas
- vendor checker
- dependencies
- required binary/package assets

결과:

```text
READY_FOR_TRUSTED_SENSOR
또는
BLOCKED_DISTRIBUTION_INCOMPLETE
```

## 7. P2 — 의미론적 버그 탐지와 routing 성능을 분리해서 평가할 필요

실사용에서 다음 유형의 문제는 상위 의미론 검토에서 발견됐다.

예: synthetic runner가 현재 process와 실제 spawn할 `powershell.exe`를 동일 executable로 가정해 path/hash mismatch가 날 수 있는 문제.

반면 CodeDiff는 해당 수정이 security boundary에 속한다는 것을 잘 분류하고 더 높은 검토 단계로 올리는 역할을 했다.

따라서 성능 평가는 최소 두 축으로 분리하는 것이 좋다.

1. **Finding discovery**
   - 실제 결함을 직접 발견했는가
2. **Review routing**
   - 변경의 위험도를 적절한 검토 레벨로 올렸는가

두 점수를 합치면 도구의 강점이 흐려진다.

## 8. P2 — 향후 precision/recall에 가까운 실측 권고

앞으로 실제 프로젝트 5~20개 변경을 대상으로 finding source를 태깅하면 유용하다.

```text
CODEDIFF
SEMANTIC_REVIEW
TEST
SANDBOX
ADVERSARIAL_REVIEW
POST_MERGE
```

그리고 다음을 집계한다.

- CodeDiff direct discoveries
- CodeDiff escalation-only successes
- false positives
- false negatives
- protected-path misses
- test weakening catches
- post-review escaped defects

이를 통해 단순 체감이 아니라 실제 precision/recall에 가까운 지표를 만들 수 있다.

## 9. 비결함으로 분리한 사항

아래 항목은 도구 결함으로 보지 않았다.

### 컨테이너 git clone DNS 실패

현재 실행환경에서 `github.com` DNS 해석이 되지 않아 일반 `git clone`이 실패했다.

이는 execution environment limitation으로 분류했으며 PR-with-codediff-finder 자체의 결함으로 보지 않는다.

## 10. 실사용 결론

현재 v2.5를 다음 위치에 두는 것이 가장 적절했다.

```text
code change
  -> normal tests
  -> PR-with-codediff-finder SHADOW sensor
  -> semantic review
  -> adversarial review when escalated
  -> evidence package
```

즉 이 도구는 **최종 승인자보다 변경 감시 레이더 + risk router + lineage/evidence generator**로 사용할 때 가치가 높았다.

특히 멀티에이전트나 반복 자동 수정 환경에서는:

- 무엇이 바뀌었는지
- 어떤 변경을 높은 단계로 보내야 하는지
- 테스트 약화가 있었는지
- 어떤 baseline/head를 검토했는지

를 지속적으로 고정하는 데 효과가 있다.

## 11. 제안 우선순위

### P1
1. trusted TextDiff original asset 재현 가능하게 제공
2. 공식 degraded sensor mode + `trusted_for_gate=false` 계약

### P2
3. project protected-path overlay
4. usage/problem log schema
5. distribution self-verifier
6. finding discovery와 routing 성능 지표 분리
7. 실사용 precision/recall benchmark 축적

---

이 문서는 v2.5를 실제 보안 경계 코드 작업에 SHADOW 방식으로 적용하면서 얻은 피드백이다.  
관찰된 장점과 문제를 분리했으며, environment limitation은 tool defect로 계산하지 않았다.
