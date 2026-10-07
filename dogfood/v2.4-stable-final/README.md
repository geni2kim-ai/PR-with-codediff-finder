# Stable v2.4 dogfood evidence

This bundle preserves the stable-v2.4 SHADOW policy-routing evidence for the final v2.5 code candidate (`864ef63404f3b9997ce123a661afdf0a8056efc8`).

Scope:
- reviewers in this bundle are deterministic `mock_reviewer --mode pass` workers;
- therefore this proves sensor binding, escalation routing and governance floors, not semantic approval by a real L1/L2/Adversarial model;
- the final stable result is `HUMAN_REQUIRED`, required `HUMAN`, achieved `ADVERSARIAL`, gate `action_required`;
- see `../../DOGFOOD_V2.4_TO_V2.5_KO.md` for the narrative and limitations.
