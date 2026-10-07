# CodeDiff 실사용 피드백 — protected-path phase alias 누락

- 날짜: 2026-10-07
- CodeDiff 코드 baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- 적용 work unit: R7A real-workload discovery preparation
- 분류: `POLICY_GAP / FALSE_NEGATIVE_RISK`
- 상태: `OPEN → LOCAL OVERLAY MITIGATED`
- authority effect: `NONE`

## 관찰

Synapse용 overlay에서 보안 경계를 다음처럼 보호하고 있었다.

```yaml
adversarial_floor_paths:
- r6/**
- r7/**
```

다음 실제 work unit 디렉터리는 단계명을 더 구체화해 `r7a/**`로 설계했다.

현재 path matcher 기준으로:

```text
r7/windows/x.ps1  -> r7/** MATCH
r7a/windows/x.ps1 -> r7/** NO MATCH
```

즉 R7의 세부 단계명을 디렉터리 이름에 붙이는 순간 adversarial floor에서 빠질 수 있다.

## 영향

이 문제는 CodeDiff core matcher 결함이라기보다 **project overlay taxonomy의 exact-pattern 취약성**이다.

하지만 자동화된 다단계 개발에서는 다음처럼 흔히 발생할 수 있다.

```text
r7/**
r7a/**
r7b/**
r7_hotfix/**
r7_retest/**
```

보호 정책이 `r7/**` 하나만 알고 있으면 새 하위 단계 naming이 별도 top-level path로 생길 때 false-negative routing 위험이 있다.

## 재현

Python fnmatch 기준:

```python
fnmatch.fnmatchcase("r7a/windows/x.ps1", "r7/**") == False
fnmatch.fnmatchcase("r7/windows/x.ps1", "r7/**") == True
```

## 로컬 보완

R7A 후보에서는 overlay를 다음처럼 확장한다.

```yaml
adversarial_floor_paths:
- r7/**
- r7a/**
- r7b/**
```

또는 프로젝트 구조가 허용한다면 모든 단계를 실제 `r7/` 하위로 두는 것이 더 안전하다.

예:

```text
r7/a/**
r7/b/**
```

## upstream 권고

프로젝트 overlay 작성 가이드에 다음 중 하나를 권장한다.

1. phase family는 top-level alias를 늘리지 말고 공통 root 하위에 둔다.
2. alias를 사용하는 프로젝트는 explicit family list를 정책 테스트로 고정한다.
3. protected-path policy 자체에 regression fixtures를 둔다.

예:

```text
expected_adversarial:
- r7/a/windows/x.ps1
- r7/b/windows/x.ps1
- r7a/windows/x.ps1  # alias를 허용한다면 명시
```

정책 테스트는 새 work-unit 디렉터리를 만들 때 자동으로 실행되어야 한다.

## 성능 관찰

CodeDiff의 path routing 자체는 deterministic해서 유용하지만, **정책에 등록되지 않은 naming variation은 당연히 감지할 수 없다.**

따라서 성능 평가는:
- matcher 정확성
- protected-path taxonomy coverage

를 분리해야 한다.

이번 finding은 후자에 해당한다.

## 결론

`r7/**` 보호만으로 `r7a/**`를 보호한다고 가정하면 안 된다.

다단계/멀티에이전트 프로젝트에서는 phase naming convention과 protected-path policy를 함께 테스트하는
작은 regression suite가 필요하다.
