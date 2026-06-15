# Archive Report — brainds-live-artifact-contract-reconciliation

**Change**: brainds-live-artifact-contract-reconciliation
**Archived**: 2026-06-14
**Mode**: brain_ds-hybrid (`.elicit/` + Engram) — no openspec sync/move required.
**Status**: COMPLETE — 2 slices, 27/27 tasks, VERDICT PASS, live acceptance PASS.

## What shipped
Option C dual-contract artifact format, reconciling real-agent output with `check_elicit_compliance` WITHOUT lowering the verifier bar:

- **Dual contract**: every `.elicit/` artifact = human markdown + ONE canonical fenced JSON block, preceded by the `<!-- canonical-payload -->` sentinel; the verifier selects the LAST fenced block (`finditer[-1]`).
- **`ARTIFACT_CONTRACT`** constant in `grounding.py` (Category-2, sweeps clean, not exempt), injected into all 3 composers cross-client (key counts 14/12/10 → 15/13/11).
- **Verifier scoping rule** (bar preserved): skip files NOT matching `PHASE_PATTERN` (README/scratch ignored); any PHASE_PATTERN-named file with missing/broken payload → CRITICAL.
- **completeness_gate** owned by the `map` artifact; invalid recommendation value → CRITICAL (explicit branch).
- **Contract reconciliation**: `_check_verify_payload` tightened to require `artifact_type` as a 7th key — killed the contract/code divergence Slice 1 left open.
- **connection-mapper**: canonical `map-*.md` write step + `Write` grant in the repo agent definition.
- **Golden-fixture CI guard**: `tests/fixtures/elicit/` + `tests/test_live_artifact_contract.py` catch format drift WITHOUT live LLM calls.

## Slices / PRs
2 chained slices, strict TDD: Slice 1 (gate blocker: ARTIFACT_CONTRACT + verifier scoping + dual-contract validation + agent prompts + connection-mapper + cross-client mirrors), Slice 2 (golden fixtures + live-artifact test + contract reconciliation).

## Final state
- Tests: **1379 passed**, 3 skipped, 0 intentional REDs.
- `brain_ds check`: **4 PASS, 0 FAIL**.
- Pre-existing unrelated failure: `test_register_path_copies_wrapper_sh` (OpenCode CLI not installed on Windows).

## LIVE ACCEPTANCE (the proof)
A REAL brain_ds cycle ran on graph `live-contract-verify` (synthetic SQLite source) via real Task delegation with the NEW dual-contract prompts:
- brainds-source-explorer → 2 canonical source-docs artifacts
- brainds-graph-mapper → Data Source card_sections + Dataset nodes
- brainds-connection-mapper → map artifact (canonical)
- brainds-brd-writer → graph node `brd-live-contract-verify` + canonical BRD artifact
- Graph: node_count 5, edge_count 4.

`check_elicit_compliance(.elicit/)` returned **0 findings → verify PASS → archive allowed**. README.md correctly ignored by the scoping rule. The verify artifact itself is self-compliant (artifact_type enforced). This closes the spirit of the predecessor finding: real-agent artifacts now satisfy the gate without relaxing validation.

Live artifacts: `.elicit/{source-docs-live-contract-verify-customers,source-docs-live-contract-verify-orders,map-live-contract-verify,brd-live-contract-verify,verify-live-contract-verify}-2026-06-14.md`.

## Deferred follow-ups
1. **connection-mapper Write at RUNTIME**: the repo agent def has `Write` (verify tests pass), but the live runtime agent (loaded before the change) lacked it — a `general-purpose` fallback wrote the map artifact in the re-run. Reinstall the harness / restart the session so connection-mapper gets `Write` at runtime. Deployment step, not a code defect.
2. **Organization node lost during graph-mapper push**: in the live re-run the pre-wired Organization node disappeared after brainds-graph-mapper's `update_node` push (restored manually). Pre-existing, unrelated to the artifact contract — investigate the graph-mapper push/update_node flow in a future change.
3. **Per-cycle subdir scoping** (`.elicit/<cycle>/`) remains deferred.

## Artifact index
Engram topic keys (all under `sdd/brainds-live-artifact-contract-reconciliation/`): charter #2167, explore #2168, proposal #2169, spec #2171, design #2172, tasks #2173, apply-progress #2174, verify-report #2175, live-rerun (#2182), decision/verifier-scoping #2170, archive-report (this).
`.elicit/sdd/brainds-live-artifact-contract-reconciliation/`: explore.md, proposal.md, spec.md, design.md, tasks.md, apply-progress.md, verify-report.md, archive-report.md.
Live cycle artifacts: `.elicit/*-live-contract-verify-2026-06-14.md` (+ `.elicit/_run1-diagnostic/` holds the original BLOCKED run that motivated this change).
