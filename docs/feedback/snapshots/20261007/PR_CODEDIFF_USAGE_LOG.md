# PR_CODEDIFF usage/problem log — compact checkpoint

Checkpoint: 2026-10-07 / 42 entries
Stable baseline: `69978ff50bc4003d6d73b8219790106846220f72`

This compact view preserves kind/severity/source/summary. The exact full append-only record is `PR_CODEDIFF_USAGE_LOG.jsonl`.

| # | kind | severity | source | summary |
|---:|---|---|---|---|
| 1 | `ENVIRONMENT_LIMITATION` | medium | execution-container | git clone of public PR-with-codediff-finder failed because container DNS could not resolve github.com |
| 2 | `UPSTREAM_PACKAGING_GAP` | high | PR-with-codediff-finder@69978ff5 | textdiff_adapter.py requires vendor/TextDiffChecker_v1_4_6_original.zip but public tree and code search contain no such file |
| 3 | `PROJECT_ADAPTATION` | medium | protected-path-policy | default auth/security protected-path taxonomy does not classify this project's r6/** authentication boundary |
| 4 | `CODE_FINDING` | medium | Leonardo manual review during diff integration | R6 synthetic harness derived expected client executable from the current process but spawned powershell.exe explicitly |
| 5 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 6 | `INTEGRATION_SELF_CHECK` | high | R6.1 packaging integration | embedded policy_engine.py initially failed the pinned upstream SHA check during self-validation |
| 7 | `HOST_HARNESS_INTERACTION` | medium | YM R6 Windows sandbox | Start-Process child reported HasExited=True while ExitCode was unavailable/empty |
| 8 | `EVIDENCE_PACKAGING_GAP` | high | YM R6 returned package | adapted runner that produced the passing run was described but not included |
| 9 | `EVIDENCE_PACKAGING_GAP` | medium | YM R6 returned package | negative evaluator exit code 2 was not preserved in a dedicated artifact |
| 10 | `MASKING_PROVENANCE_GAP` | medium | YM R6 returned package | SID values were replaced consistently with SID_MASKED without preserving raw-file digest lineage in the distributable |
| 11 | `PRIVACY_LOG_LEAK` | low | YM R6 returned package | server stdout kept local workspace path C:\Genie\opencode\... |
| 12 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 13 | `SELF_CHECK_TRAILING_WHITESPACE` | low | R6.2 git diff --check | handoff work packet contained three Markdown lines with trailing whitespace |
| 14 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 15 | `WINDOWS_LAUNCH_PLUMBING_DEFECT` | high | YM R6.2 unchanged packaged runner | multi-line here-string encoded with -EncodedCommand lost continuation semantics; mandatory server parameters were not bound |
| 16 | `EVIDENCE_QUALITY_SUCCESS` | info | YM R6.2 returned package | runner source, local patch, raw-to-masked SHA lineage, redaction documentation, and negative exit codes were all returned |
| 17 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 18 | `SELF_TEST_FALSE_POSITIVE` | low | R6.3 static contract test | initial test searched past the server-command expression and incorrectly treated the CR/LF guard's PowerShell backticks as continuation syntax |
| 19 | `SELF_CHECK_TRAILING_WHITESPACE` | low | R6.3 package quality check | Markdown hard-break trailing spaces caused the initial diff-quality check to be non-clean |
| 20 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 21 | `EVIDENCE_PRIVACY_FALSE_NEGATIVE` | high | YM R6.3 distributable byte-level recheck | PowerShell CLIXML stderr retained account/profile/workspace metadata although masking documentation claimed raw identifiers were absent |
| 22 | `PROTECTED_PATH_ALIAS_GAP` | medium | Synapse CodeDiff overlay | r7/** does not match a top-level r7a/** work-unit directory |
| 23 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 24 | `POWERSHELL_AUTOMATIC_VARIABLE_COLLISION` | high | YM R7A packaged collector | function parameter $Pid collided with read-only automatic variable $PID and blocked collection before measurement |
| 25 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 26 | `MULTIHOST_PRIVACY_SOURCE_COVERAGE_GAP` | medium | R7C evidence packaging design | current-host-derived privacy patterns cannot prove privacy coverage for evidence originating on other hosts |
| 27 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 28 | `REFERENCE_ORDER_FALSE_NEGATIVE_RISK` | high | R7C semantic closeout review | filename heuristic ran before runtime reference matching, so a neutral-named controlled launcher could be omitted before linkage |
| 29 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 30 | `RELATIVE_SEARCH_ROOT_PORTABILITY_GAP` | medium | R7D locator semantic review | resolved root was looked up in the original unresolved search_roots list; relative-root hit can raise ValueError |
| 31 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 32 | `CHILD_PARENT_BINDING_EVIDENCE_GAP` | medium | R8 synthetic launcher closeout review | R8 recorded Process.Start PID and process-instance rechecks but did not bind OS-observed ParentProcessId to launcher PID |
| 33 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 34 | `REVIEW_TREE_TEST_ARTIFACT_POLLUTION` | medium | R8.1 CodeDiff closeout self-check | pytest-generated __pycache__/*.pyc artifacts entered the temporary git review tree and inflated CodeDiff inventory |
| 35 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 36 | `OPAQUE_CHILD_PAYLOAD_TRUST_BOUNDARY_GAP` | high | R8B semantic review | top-level authority-field filtering is not sufficient if child-provided structured output is later recursively interpreted |
| 37 | `SHARED_INTERPRETER_IDENTITY_AMBIGUITY` | high | R9 mediator authentication preparation | PowerShell mediator source identity is not uniquely observable from powershell.exe path/hash plus a shared user SID |
| 38 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 39 | `POWERSHELL51_CRYPTO_API_PORTABILITY_GAP` | high | R8B.1 Windows compatibility review | draft used Convert.ToHexString and SHA256.HashData which are not guaranteed on Windows PowerShell 5.1/.NET Framework |
| 40 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
| 41 | `UNBOUNDED_DUAL_STREAM_CHILD_IO` | high | R8B.1 Windows-success closeout semantic review | PowerShell prototype used unbounded stdout MemoryStream and sequential stderr drain; unsafe for future untrusted child output |
| 42 | `DEGRADED_SENSOR_RUN` | warning | PR-with-codediff-finder-bridge | official stable sensor unavailable |
