# v2.5 stable → v2.6 candidate SHADOW dogfood

This bundle was produced by the **v2.5 stable harness**, not by the v2.6 candidate itself.

Purpose: verify deterministic evidence binding and authority routing while candidate v2.6 is treated as untrusted code. Review workers were deterministic `mock_reviewer --mode pass`; therefore this is **not semantic approval by a real model**.

Observed stable-v2.5 result:

- files changed: 50
- changed lines: 2,293
- sensor quality: `HEURISTIC`
- `trusted_for_gate=true`
- required authority: `HUMAN`
- achieved authority: `ADVERSARIAL`
- state: `HUMAN_REQUIRED`
- gate: `action_required`
- key reasons: governance change, protected Adversarial path, test-integrity finding

The `base_sha` and `head_sha` stored in these JSON files are commits in a temporary reproducibility repository created only for this dogfood run; they are **not GitHub repository commit IDs**. `reviewed-snapshot.sha256` records the source-file bytes that were reviewed, excluding this dogfood directory itself, `MANIFEST.sha256`, and Python bytecode caches.

Historical absolute workspace paths inside task JSON are intentionally preserved because changing them would invalidate bound digests. They are ephemeral sandbox paths, not deployment paths or secrets.
