# Historical stable-v2.4 dogfood evidence

This directory is retained as historical v2.4 → v2.5 SHADOW routing evidence.

- Review workers were deterministic `mock_reviewer --mode pass` workers.
- It demonstrates sensor binding, escalation routing and governance floors, not semantic approval by a real reviewer model.
- The stored result is `HUMAN_REQUIRED`, required `HUMAN`, achieved `ADVERSARIAL`, gate `action_required`.
- The commit identifier recorded in the historical narrative was producer-reported; this package does not include the original Git history needed to independently verify that commit identity.
- `textdiff-evidence.json` is the canonical evidence copy in this directory.
