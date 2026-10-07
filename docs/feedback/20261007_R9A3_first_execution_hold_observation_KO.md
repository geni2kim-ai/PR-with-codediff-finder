# CodeDiff 피드백 — R9A.3 first-execution transient hold observation

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: R9A.3 native-handle matrix closeout
- 분류: `ENVIRONMENT_LIMITATION / PERFORMANCE_OBSERVATION`
- 상태: `OBSERVED / ATTRIBUTION_UNVERIFIED`

## 관찰

YM에서 brand-new R9A.3 mediator binary의 첫 normal 실행은 child execution timeout으로 종료됐다.
동일 binary와 동일 arguments를 한 번 더 실행하자 normal receipt가 생성됐고 이후 20/21/22 negative
matrix도 재현됐다.

현재 evidence만으로 특정 endpoint 제품, reputation scan, signing policy 또는 다른 원인을 확정할 수 없다.

따라서 원인 attribution은 `UNVERIFIED`로 유지한다.

## 영향

- confirmatory run 이후 functional matrix는 PASS.
- 첫 실행 latency가 실제 운영 startup budget을 초과할 가능성은 남음.
- 보안 gate를 통과시키기 위해 무제한 재시도하는 근거로 사용하면 안 됨.

## 권고

향후 package에서는:
- 첫 실행과 confirmatory 실행을 별도 evidence로 보존
- 재시도 횟수 상한 유지
- cold-start latency 측정
- live authentication timeout과 workload execution timeout을 분리
- 원인이 입증되기 전 특정 보안 제품/정책 명칭으로 귀속하지 않기

## CodeDiff 관점

이는 정적 diff로 직접 판단하기 어려운 environment/performance observation이다.
Windows sandbox evidence가 필요한 항목으로 별도 추적하는 것이 적절하다.
