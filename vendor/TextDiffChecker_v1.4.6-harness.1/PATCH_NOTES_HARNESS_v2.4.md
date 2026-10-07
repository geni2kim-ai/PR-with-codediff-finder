# TextDiffChecker Harness Patch v2.4

Base product: TextDiffChecker v1.4.6
Harness API: `1.4.6-harness.1`

Harness-specific changes:
- algorithm trace and conservative quality classification;
- `DIFF-FALSE-EXACT` regression coverage;
- trace API now preserves the original opcode API's inline detail and final cancellation semantics;
- patch files are regenerated from the bundled original v1.4.6 zip and verified byte-identical after application.

The GUI/product behavior is not treated as the review authority. The harness consumes metadata/opcodes/trace through the adapter and independently binds results to Git.
