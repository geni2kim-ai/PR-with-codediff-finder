# R9B.4.3 HUMAN-only packet — evidence completeness and traceability gaps

- date: 2026-10-08
- target: `r9b43_v26_human_only_decision_packet_v2_20261008.zip`
- review baseline: `PR-with-codediff-finder v2.6 hardening/v2.6@41369e4a94ee9ab85c48ba117319658248e59ece`
- classification: `HUMAN_REVIEW_EVIDENCE_GAP / TRACEABILITY_GAP / CLEANUP_VERIFIER_GAP`
- authority effect: NONE
- R9C: BLOCKED

## Adopted findings

### P1 — HUMAN packet omits runtime evidence needed for replay/cleanup questions

The sealed review set contains only the normal-run cleanup receipt and offline re-bound evidence. It does not include:
- live replay-ledger consumption evidence;
- immediate duplicate denial;
- production timeout cleanup evidence;
- child-tree cleanup evidence;
- wrong-SID cleanup evidence.

Therefore Q5/Q6 cannot be answered from the HUMAN packet alone even though those artifacts exist in the R9B.4.2 Windows return.

### P2 — question traceability is stale

The prior traceability table follows an older question numbering and references files that are not present in the sealed review set.

A replacement traceability table must:
- use the current V2 question numbering;
- point only to files actually present in the HUMAN packet or explicitly packaged supplements;
- mark known residuals vs directly reproduced evidence.

### P3 — exact verifier/evaluator toolchain not self-contained in review subject

The sealed review ZIP omits:
- evaluator;
- `verify_review_safe_set.py`;
- measurement harness;
- replay implementation;
- mediator/child sources.

A HUMAN reviewer should not need earlier packages to reproduce the supplied verification.

The review bundle must include exact source/tool bytes plus hashes without modifying the already sealed runtime evidence.

### P4 — R9B.4.1 -> R9B.4.2 PID contract change lacks explicit lineage in HUMAN handoff

The verifier source changed to add:
- `capture.verifier.pid`;
- `completion.verifier_pid`.

Include the exact 4.1 -> 4.2 patch/change note and tool/source hashes in the review packet.

### P5 — some server metadata are pass-through claims

`verifier_source_sha256`, `preflight_sha256`, `run_context_sha256`, and `build_receipt_sha256` are passed to the verifier process and serialized; they are not independently measured by the verifier itself.

Do not describe these as server-observed measurements. Classify them as bound inputs checked elsewhere in the chain.

### P6 — evaluator cleanup validation is too narrow

For cleanup evidence, the evaluator currently does not reject:
- non-empty `child_pids_remaining_after`;
- failed bounded wait;
- suspicious `pid_reused_after`;
- inconsistent tree-kill fields.

R9B.4.4 should validate these fields conservatively where they are applicable.

### P7 — same-user rehearsal residual

ACL/SID evidence does not demonstrate separation between distinct human/user principals. This remains a disclosed rehearsal residual and should not be overclaimed as subject authentication.

### P8 — transformation receipt does not enumerate all rebinding changes

The review-safe transformation receipt enumerates direct privacy-field changes but not all derived hash rebinding changes in preflight/run_context/harness/completion.

For HUMAN review, include a separate rebinding map that lists every changed derived field and old/new digest relation without exposing raw SID/path values.

### P9 — producer-owned external anchor provides immutability, not reviewer independence

The GitHub anchor is useful as an immutable publication/binding. It must not be described as an independent reviewer attestation.

## Required remediation

Create R9B.4.4 with two bounded parts:

1. **Evaluator hardening only**
   - strengthen cleanup-receipt checks;
   - no new authority;
   - re-run static/clean-extract tests;
   - re-run Windows only if the evaluator change requires a new accepted result.

2. **HUMAN review-completeness bundle**
   - exact evaluator, verifier, harness, replay implementation, mediator/child source, and hashes;
   - R9B.4.2 runtime evidence for live replay, timeout cleanup, child-tree, wrong-SID and negative matrices;
   - exact R9B.4.1 -> R9B.4.2 change lineage;
   - V2-correct question traceability;
   - complete rebinding map;
   - explicit classification of measured vs passed-through fields;
   - anchor semantics = immutable producer publication, not independent attestation.

## Gate

Current HUMAN packet is not rejected, but it is insufficiently self-contained for efficient independent review.

R9C remains blocked.
