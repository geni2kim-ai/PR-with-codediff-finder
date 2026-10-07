# Adjudication and Standard Evolution

A higher reviewer is not only a PR reviewer; it is a label-quality step for the review system.

1. L1/L2 disagreement, novel family, sensor conflict, post-merge incident or random audit creates an adversarial case.
2. Adversarial/Human writes a validated `adjudication` record identifying the final verdict, wrong layer(s), failure family, standard gap and fixture recommendation.
3. If and only if `standard_gap=true`, `propose_standard_candidate.py` can create a `PROPOSED` rule candidate.
4. A candidate cannot self-approve. The schema fixes `approval.required=[HUMAN,CODEOWNER]` and `approved=false`.
5. After human approval outside this package, update the canonical standard/policy through its normal governed PR and add a regression fixture where feasible.

This prevents Leonardo/Davinchi or a reviewer from changing the rule that judges itself.
