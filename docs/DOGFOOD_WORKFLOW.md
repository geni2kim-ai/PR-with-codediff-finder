# Stable-Baseline Dogfood Workflow

Use the last accepted harness version as the reviewer of the next candidate.

1. Record stable baseline package/hash and candidate base commit.
2. Make one bounded candidate change and commit it.
3. Run the stable TextDiff adapter over baseline commit → candidate HEAD.
4. Run the stable cycle in SHADOW with L1/L2/Adversarial available as policy requires.
5. Preserve `required_level`, `achieved_level`, reasons, evidence digest and changed paths.
6. Treat governance/policy/schema changes as human-authority changes even when all automated reviewers pass.
7. Add any dogfood-discovered defect as a regression fixture before continuing.
8. Repeat after each meaningful change batch.
9. Final candidate may run its own tests, but final approval authority remains outside the candidate.

Backdata should distinguish:
- baseline reviewer version;
- candidate version;
- sensor/tool digest;
- reviewer worker command digest;
- model/prompt/policy/standard digests;
- upper-authority adjudication;
- eventual outcome/post-merge status.


## v2.7 downstream/recovery dogfood additions

For every meaningful hardening batch, also exercise the downstream boundary after the review itself:

10. Mutate live policy after the cycle and verify routing uses the cycle's frozen `effective-policy/`.
11. Mutate caller standards/spec/test after the cycle and verify routing uses the cycle's frozen `trusted-inputs/`.
12. Corrupt or delete a referenced case-bank artifact and verify recovery refuses to requeue the immutable packet.
13. Convert every reproduced dogfood failure into an executable regression before closeout.


## v2.7 review-campaign/time dogfood

Exercise loop control as part of dogfood:

14. NOTE_ONLY scenario: L1 returns only nit/minor. Confirm no L2 is launched solely for that finding, no remediation retry is allowed, and the item remains in `review-notes.json`.
15. Major-remediation scenario: L1 major → L2 confirmation → one batched source change → new HEAD → one re-review. Confirm a clean second attempt closes the campaign.
16. Repeated-major scenario: if the same material finding key remains after the batched fix, confirm the second completed material attempt becomes `HUMAN_REQUIRED` rather than starting another automatic fix.
17. Unchanged-HEAD retry scenario: a completed material attempt must reject `--retry` until HEAD changes.
18. Different-material scenario: new material families may consume the remaining attempt budget, but the campaign must stop after the third worker-bearing attempt.
19. Record agent-stage count and timeout ceiling in `review-budget.json`; distinguish review-worker time from CI/package validation time.

20. SHADOW WAITING_L2 resume: make L1 observable, stop at WAITING_L2, then retry with L2 available. Confirm the prior L1 result is provenance-compatible, reused once, and the L1 worker is not executed again.
21. Confirm `review-budget.json` counts a reused lower stage separately and charges timeout budget only for newly executed workers.
22. Change any reusable-stage binding/provenance/trusted-ref input and confirm reuse is rejected rather than silently accepted.
