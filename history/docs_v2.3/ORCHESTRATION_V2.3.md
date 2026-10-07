# Local Review Orchestration v2.3

## Goal
v2.3 turns the v2.2 sensor/policy components into a repeatable local review cycle. It does not embed a specific model provider. Each L1/L2/Adversarial node is connected through a process contract: task JSON on stdin, stage-result JSON on stdout.

## Information separation
- **L1** receives evidence, changed paths and trusted refs.
- **L2** is spawned in a fresh process and receives the same evidence but **no L1 result or conclusion**.
- The harness compares L1/L2 only after both finish.
- **Adversarial** receives bounded L1/L2 result references because it adjudicates the disagreement; it still starts in a fresh review context.
- Human authority remains external and cannot be synthesized by the reviewer process.

`reviewer-task.schema.json` and `reviewer-stage-result.schema.json` are the worker protocol. `review-cycle.schema.json` is the orchestration snapshot.

## Head binding
The harness checks `git rev-parse HEAD` before review and again after all worker calls. A change at either point makes the cycle `STALE` and the predicted gate `cancelled`. No PASS is reusable across a new head.

## Worker execution
`run_review_cycle.py` uses `subprocess.run(..., shell=False)`, a bounded timeout/output size, and an environment allowlist. This removes common credential leakage through environment variables but **does not itself provide an OS network namespace or filesystem sandbox**.

Therefore the shipped configuration is `mode: shadow`. `ENFORCED` mode refuses to start unless the routing policy attests environment secret stripping, network denial, workspace filesystem scoping, and fresh-model-session isolation for L2/Adversarial.

## Shadow semantics
Shadow cycles calculate the conclusion that an enforced gate would have produced, but `gate_effective=false`. `render_github_check.py` forces any shadow check preview to GitHub conclusion `neutral` and prefixes the check name with `[SHADOW]`.

This is intentional: first collect real local coding backdata and calibrate L1/L2/Adversarial behavior before merge enforcement.
