# CodeDiff 실사용 피드백 누적 인덱스 — 2026-10-07 checkpoint

이 문서는 `PR-with-codediff-finder` v2.5를 Synapse/Agent-OTP 코드 작업에 SHADOW 적용하면서 누적된 실사용 피드백과 usage/problem log의 checkpoint다.

## 기준

- CodeDiff stable code baseline: `v2.5`
- baseline commit: `69978ff50bc4003d6d73b8219790106846220f72`
- snapshot source work unit: `R8B2_BOUNDED_IO_AND_R9A_DEDICATED_MEDIATOR_CANDIDATE`
- usage/problem log entries: **42**
- JSONL SHA-256: `94fb709d6564f34c0dd8a13fbe76fb2d0aea716aeaa4cd220d888f63b463d2f2`
- Markdown SHA-256: `59c170be6e0917ab0c31f8e36644e50812353aa2b6f2908d4045f2c007228560`
- trusted sensor state: official TextDiff asset not materialized; degraded SHADOW results remain `trusted_for_gate=false`
- authority effect of the reviewed Synapse workflow: `NONE`

## 누적 로그 요약

- severity counts: `high=11`, `info=1`, `low=4`, `medium=11`, `warning=15`
- degraded sensor runs recorded: **15**
- 주요 finding 축: reproducibility, project policy taxonomy, PowerShell/runtime portability, evidence privacy, process lineage, review-tree hygiene, opaque-data trust boundary, OS-observable workload identity, child I/O resource bounds

실제 append-only 원장은 다음 snapshot에 고정한다.

- [`PR_CODEDIFF_USAGE_LOG.md`](snapshots/20261007/PR_CODEDIFF_USAGE_LOG.md) — compact human-readable rendering
- [`CHECKPOINT.json`](snapshots/20261007/CHECKPOINT.json) — snapshot digest / counts / baseline metadata

## 피드백 문서 인덱스

| 문서 | 주제 | 핵심 |
|---|---|---|
| [`REALWORLD_INTEGRATION_FEEDBACK_20261007_KO.md`](../REALWORLD_INTEGRATION_FEEDBACK_20261007_KO.md) | Initial real-world integration review | Baseline reproducibility / degraded-mode contract / overlay / metrics |
| [`CODEDIFF_CONTINUOUS_FEEDBACK_POLICY_20261007_KO.md`](../CODEDIFF_CONTINUOUS_FEEDBACK_POLICY_20261007_KO.md) | Continuous feedback policy | Per-turn feedback recording rule |
| [`20261007_R63_evidence_masking_codediff_feedback_KO.md`](20261007_R63_evidence_masking_codediff_feedback_KO.md) | R6.3 evidence masking | CLIXML/privacy seal false-negative |
| [`20261007_R7A_protected_path_alias_gap_KO.md`](20261007_R7A_protected_path_alias_gap_KO.md) | R7A protected-path alias | `r7/**` not covering `r7a/**` |
| [`20261007_R7A_powershell_automatic_variable_collision_KO.md`](20261007_R7A_powershell_automatic_variable_collision_KO.md) | R7A PowerShell `$PID` collision | Language-semantic static-analysis gap |
| [`20261007_R7C_multihost_privacy_coverage_gap_KO.md`](20261007_R7C_multihost_privacy_coverage_gap_KO.md) | R7C multi-host privacy coverage | Source-host privacy provenance gap |
| [`20261007_R7C_reference_first_discovery_gap_KO.md`](20261007_R7C_reference_first_discovery_gap_KO.md) | R7C reference-first discovery | Filename-prefilter false-negative risk |
| [`20261007_R7D_relative_search_root_portability_gap_KO.md`](20261007_R7D_relative_search_root_portability_gap_KO.md) | R7D relative search-root portability | Path normalization/runtime bug |
| [`20261007_R8_launcher_parent_binding_gap_KO.md`](20261007_R8_launcher_parent_binding_gap_KO.md) | R8 launcher parent binding | OS-observed parent PID evidence gap |
| [`20261007_R81_test_artifact_pollution_KO.md`](20261007_R81_test_artifact_pollution_KO.md) | R8.1 review-tree pollution | pytest artifacts contaminating CodeDiff inventory |
| [`20261007_R8B_opaque_payload_trust_boundary_gap_KO.md`](20261007_R8B_opaque_payload_trust_boundary_gap_KO.md) | R8B opaque payload boundary | Structured child-data trust gap |
| [`20261007_R8B1_powershell51_crypto_api_gap_KO.md`](20261007_R8B1_powershell51_crypto_api_gap_KO.md) | R8B.1 PowerShell 5.1 crypto compatibility | Runtime API portability gap |
| [`20261007_R9_shared_interpreter_identity_gap_KO.md`](20261007_R9_shared_interpreter_identity_gap_KO.md) | R9 shared interpreter identity | OS-observable workload identity ambiguity |
| [`20261007_R8B1_bounded_child_io_gap_KO.md`](20261007_R8B1_bounded_child_io_gap_KO.md) | R8B.1 bounded child I/O | Resource-boundary / dual-stream deadlock risk |

## 현재 판단

1. CodeDiff는 **change surveillance / risk routing / evidence lineage**에는 강한 편이다.
2. 실사용에서 발견된 주요 결함 상당수는 **semantic review / Windows sandbox / packaging self-check**가 잡았다.
3. 따라서 현재 권장 흐름은 `tests -> CodeDiff SHADOW -> semantic review -> adversarial/human review -> evidence package`다.
4. degraded sensor 결과는 trusted PASS로 승격하지 않는다.
5. 향후 성능 평가는 `CodeDiff direct finding`과 `CodeDiff routing success`를 분리해서 기록한다.

## 운영

이 checkpoint 이후에도 `CODEDIFF_CONTINUOUS_FEEDBACK_POLICY_20261007_KO.md`에 따라 **새 발견이 있는 턴에만** 개별 피드백 문서를 추가한다. 다음 checkpoint에서는 snapshot을 새 날짜/시점 경로에 추가하고 과거 snapshot은 수정하지 않는다.
