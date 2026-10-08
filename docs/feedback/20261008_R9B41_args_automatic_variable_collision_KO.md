# R9B.4.1 integration feedback — PowerShell $Args automatic-variable collision caught pre-package

- date: 2026-10-08
- work unit: R9B.4.1 packaging/authority/cleanup correction
- classification: `INTEGRATION_GAP / POWERSHELL_SEMANTIC_LINT_FINDING`
- severity: low
- status: fixed before package seal

## Finding

The new forced-timeout probe initially assigned a local variable named `$args`.

PowerShell variable names are case-insensitive, so this collides with automatic variable `$Args`.

The extended semantic lint correctly reported:

`POWERSHELL_AUTOMATIC_VARIABLE_COLLISION / assignment / variable=args`

before package sealing.

## Remediation

Renamed the local variable to `$argLine` and reran the semantic lint.

Final lint result for the corrected candidate:

`PASS / 0 findings`

## Impact

No released/issued R9B.4.1 package contained the collision. This was an integration-side defect detected during
pre-release validation, not a runtime incident.

## Process recommendation

Keep assignment-level automatic-variable lint mandatory for all new PowerShell harness/probe files, not only
function parameters.
