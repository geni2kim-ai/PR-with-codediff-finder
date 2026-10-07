# CodeDiff 피드백 — accumulated patch/log bundle retains historical local workspace path

- 날짜: 2026-10-07
- CodeDiff baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- work unit: public full-package publication to `geni2kim-ai/Extra`
- 분류: `PACKAGING_GAP / EVIDENCE_PRIVACY_GAP`
- 상태: `OBSERVED → PUBLICATION REDACTION REQUIRED`

## 관찰

R9B.2 최신 풀패키지를 public repository에 게시하기 전 byte-level privacy 재검사를 수행했다.

현재 기능 소스나 최신 R9B.2 raw evidence가 아니라, 과거 R6 계열에서 누적해 온 CodeDiff usage log 및
candidate patch 일부에 로컬 workspace 예시/경로 문자열 `C:\Genie\...`가 남아 있었다.

최신 기능 동작에는 필요하지 않으며 public artifact에 그대로 게시할 이유도 없다.

## 영향

- R9B.2 기능/검증 결과에는 영향 없음.
- private/local handoff package의 integrity에는 영향 없음.
- public `Extra` repository에 원본 누적 evidence를 그대로 올리면 불필요한 로컬 filesystem 정보가 노출됨.

## 조치

public publication용 full package를 별도로 생성한다.

- source/functionality는 변경하지 않음
- historical local workspace path literal만 `<LOCAL_WORKSPACE>`로 redaction
- public package에 별도 manifest/SHA를 생성
- original private/local package SHA와 public-safe package SHA를 README에 함께 구분 기록
- raw local registry/capture 같은 local-only evidence는 애초의 packaging policy대로 포함하지 않음

## CodeDiff 관점

diff evidence와 usage log는 시간이 지나면서 자체적으로 distribution artifact가 된다.
따라서 source code만 privacy scan할 것이 아니라 **누적 patch/log/report 전체를 distribution seal 대상으로**
검사해야 한다.
