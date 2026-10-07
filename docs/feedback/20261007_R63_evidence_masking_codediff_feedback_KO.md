# CodeDiff 실사용 피드백 — R6.3 evidence masking 검증 누락

- 날짜: 2026-10-07
- CodeDiff 코드 baseline: v2.5 / `69978ff50bc4003d6d73b8219790106846220f72`
- 저장소 현재 main: `ff0c8d00827c44299ba350b3c556e6619ff977c7`
- 적용 work unit: `YM-R6.3-UNMODIFIED-LAUNCH-RETEST`
- 분류: `EVIDENCE_GAP / PACKAGING_GAP`
- 상태: `OPEN → MITIGATION PREPARED`
- authority effect: `NONE`

## 1. 관찰

R6.3 Windows sandbox 결과 자체는 정상적으로 통과했다.

- packaged runner 무패치 실행
- `R6_SYNTHETIC_LOOPBACK_PASS`
- `WORKLOAD_PROVED_OFFLINE`
- `NOT_AUTHORIZED`
- `authority_effect=NONE`
- completion marker 검증
- negative 3건 exact DENY + exit code 2
- raw↔masked SHA lineage 포함

그러나 배포 패키지를 byte-level로 다시 검사하는 과정에서, 문서의 마스킹 주장과 실제 산출물이 일치하지 않는 항목을 발견했다.

`docs/MASKING.md`는 local workspace-root/account identifier가 배포 패키지에서 제거됐다고 설명하지만, 다음 파일의 PowerShell CLIXML 메타데이터에 식별 정보가 남아 있었다.

`deliverable/R6_server_stderr.txt`

관찰된 예:

```text
C:\Users\YSK\AppData\Local\Temp\opencode\...
User=...\YSK
Computer=...
```

stdout 본문 경로는 `REDACTED_WORKSPACE`로 바뀌었지만, stderr에 직렬화된 InformationRecord의 metadata 필드는 별도로 남았다.

## 2. 왜 단순 grep 검증이 실패했는가

PowerShell redirect 결과는 일반 텍스트뿐 아니라 CLIXML 형태의 메타데이터를 포함할 수 있다.

마스킹 로직이 주로 다음만 처리하면:

- 명시적으로 알고 있는 workspace root 문자열
- JSON SID 값
- 정상 stdout 텍스트

다음 부가 필드를 놓칠 수 있다.

- `Source`
- `User`
- `Computer`
- PowerShell host/progress metadata
- 다른 encoding(UTF-16 등)으로 저장된 로그

즉 **semantic payload만 scrub하고 serialization metadata를 검사하지 않는 gap**이 존재한다.

## 3. 영향

기능적인 R6.3 workload-capture PASS는 무효화하지 않는다.

하지만 evidence packaging 관점에서는:

1. "raw account identifier grep = 0" 같은 seal claim이 실제 bytes와 불일치할 수 있다.
2. 사용자 계정명, 로컬 temp/workspace 경로, 컴퓨터명이 외부 배포본에 남을 수 있다.
3. masking 완료 여부를 문서 선언만으로 신뢰하면 안 된다.
4. CodeDiff usage/evidence package가 장기적으로 외부 공유될 경우 metadata leakage가 누적될 수 있다.

## 4. CodeDiff 쪽 권고

CodeDiff 자체의 diff 엔진 결함은 아니지만, evidence generator / packaging workflow에 다음 검사를 넣을 가치가 있다.

### 4.1 byte-level distributable scan

최종 패키지 sealing 전에 텍스트 파일만 decode해서 검사하지 말고 raw bytes 기준으로도 forbidden token을 검색한다.

예:

```text
C:\Users\
/Users/
AppData\Local\Temp
known account name
known machine name
known workspace root
```

UTF-8, UTF-16LE, UTF-16BE 변형도 같이 생성해 검사한다.

### 4.2 PowerShell CLIXML aware scrub

`#< CLIXML` 또는 PowerShell serialized XML이 감지되면 다음 필드를 별도로 scrub한다.

- Source
- User
- Computer
- host/information/progress metadata

가능하면 배포 evidence에서는 CLIXML 전체를 보존하는 대신 필요한 stderr summary + raw digest만 남기는 방식도 고려할 수 있다.

### 4.3 masking claim must be machine-proved

문서의 다음 주장:

`RAW_IDENTIFIER_GREP_ZERO`

는 단순 narrative가 아니라 machine-readable seal result와 연결해야 한다.

예:

```json
{
  "scan_mode": "RAW_BYTES_MULTI_ENCODING",
  "forbidden_patterns": 12,
  "files_scanned": 42,
  "matches": 0,
  "status": "PASS"
}
```

### 4.4 raw↔masked lineage와 privacy scan을 분리

SHA lineage가 정확하다고 해서 개인정보 제거가 정확한 것은 아니다.

따라서:

- integrity lineage
- masking transform
- privacy leak scan

을 서로 독립적인 gate로 관리하는 것이 좋다.

## 5. 성능 관찰

이번 사례는 CodeDiff를 단순 diff reviewer보다 **evidence/package quality sensor**로 확장할 때 유용한 검증 축을 보여준다.

기존 CodeDiff가 잘하는 것:
- 변경 범위
- protected path
- review escalation
- lineage

추가하면 좋은 것:
- distributable evidence privacy scan
- encoding-aware leakage detection
- structured log metadata scrub validation

## 6. 재현 조건

1. Windows PowerShell child process stdout/stderr를 파일로 redirect한다.
2. PowerShell InformationRecord/ProgressRecord가 CLIXML 형태로 stderr에 기록된다.
3. 일반 stdout/workspace path 문자열만 masking한다.
4. 최종 ZIP의 `R6_server_stderr.txt` raw bytes를 검색한다.
5. `C:\Users\<account>`, account name, temp path가 남는지 확인한다.

## 7. 권장 후속

- R6/R7 evidence packager에 raw-byte multi-encoding privacy scanner 추가
- CLIXML metadata scrubber 또는 summary-only export 추가
- masking seal을 machine-readable artifact로 남김
- 이 검사를 CodeDiff 결과 패키지 공통 seal 단계 후보로 검토

## 결론

이번 finding은 `PR-with-codediff-finder`의 core diff algorithm 결함으로 분류하지 않는다.

대신 실제 SHADOW 운영에서 드러난 **evidence packaging / privacy verification gap**이며, 반복 자동 리뷰 환경에서는 충분히 일반화 가능한 개선 항목이다.
