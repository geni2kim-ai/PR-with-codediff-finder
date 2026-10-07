# Reviewer Calibration

`calibration_report.py` scans case-bank snapshots and reports:
- review count per authority level and model identity,
- agreement of each lower level with the highest recorded authority,
- L1→L2, L2→Adversarial and Adversarial→Human verdict reversals,
- PASS decisions followed by a post-merge incident/regression.

Agreement with a higher reviewer is **not ground truth**. Post-merge outcomes, deterministic invariants and human adjudications remain separate evidence. Use the report to select cases for cross-validation and to decide where standards or prompts need improvement, not to automatically promote a model.
