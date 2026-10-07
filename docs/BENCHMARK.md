# Benchmark / Golden Corpus v2.4

The golden set should include known-correct and known-bad PRs spanning correctness, security, spec, standards, check weakening, dependencies, migration/API breaks, injection/exfiltration attempts, governance tampering, stale head/worktree, rename-out of protected paths, symlink/submodule/binary changes, evidence tampering, large/generated files, newline/encoding cases, and sanitized historical disagreements/incidents.

Mandatory TextDiff fixtures include threshold boundaries, repetitive data, block moves, full replacement, the `DIFF-FALSE-EXACT` case, and trace-vs-original-API parity.

Benchmark repeated runs with pinned model/prompt/policy versions. Record variance, false-negative rate, false-positive rate, latency, output truncation and cost. Diff size thresholds in `limits.yml` are starting defaults only; change them through benchmark-backed owner review.
