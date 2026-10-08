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
