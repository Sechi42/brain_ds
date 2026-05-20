# Archive Report: backend-ui-contract

**Date**: 2026-05-20
**Change**: `backend-ui-contract`
**Roadmap**: `backend-migration-to-new-ui` — Phase A · #1 (observation #875)
**Artifact store mode**: hybrid (file + Engram)
**Verdict**: ✅ CLEAN PASS — 602 passed, 4 skipped, 0 failed

---

## Verification Status

| Check | Result |
|-------|--------|
| Tasks total | 22 |
| Tasks complete | 22 |
| Test suite | 602 passed, 4 skipped |
| Spec compliance | 26/26 scenarios compliant |
| CRITICAL findings | None |
| WARNING findings | None |
| SUGGESTION findings | None |
| **Verdict** | **PASS** |

## Engram Trail

| Artifact | Engram ID | Topic Key |
|----------|-----------|-----------|
| Exploration | #878 | `sdd/backend-ui-contract/exploration` |
| Proposal | #879 | `sdd/backend-ui-contract/proposal` |
| Design | #880 | `sdd/backend-ui-contract/design` |
| Spec | #881 | `sdd/backend-ui-contract/spec` |
| Tasks | #885 | `sdd/backend-ui-contract/tasks` |
| Apply progress | — | (file only, per apply-progress.md) |
| Verify report | #891 | `sdd/backend-ui-contract/verify-report` |
| Archive report | (this) | `sdd/backend-ui-contract/archive-report` |

## Delivered Behavior

### Contract additions (RENDER_CONTEXT v1.0.0)

| Field | Type | Value / Derivation |
|-------|------|-------------------|
| `RENDER_CONTEXT.contract_version` | string | `"1.0.0"` — semver, pinned by literal test |
| `RENDER_CONTEXT.meta.workspace` | object | `{ root, displayPath, project, graph }` — filesystem-derived |
| `RENDER_CONTEXT.nodes[*].score` | float [0.0, 1.0] | `max(incident edge.score)`; isolated → 0.0 |
| `RENDER_CONTEXT.nodes[*].updated_at` | ISO-8601 UTC string | `max(incident evidence.timestamp)`; fallback `meta.generated_at` |
| `RENDER_CONTEXT.nodes[*].neighbor_count` | int ≥ 0 | `len(adjacency[node.id])` |

### R08 — Tab persistence contract evidence

- `brain_ds/ui/workspace_storage_contract.py` defines `TabModel` dataclass (6 fields: `id`, `label`, `graphPath`, `active`, `closeable`, `openedAt`)
- `LOCKED_UTC_SECONDS_PATTERN` regex constant enforces `YYYY-MM-DDTHH:MM:SSZ` in `openedAt`
- localStorage keys: `brain_ds.workspace.tabs.v1` (TabModel array) and `brain_ds.workspace.history.v1` (string array, max 50, last-active-first)
- Malformed JSON recovery: reset to empty array + log, no crash
- Tests: `test_tab_model_schema_fields_documented`, `test_tab_model_opened_at_regex_is_locked_to_utc_seconds`, `test_history_payload_is_bounded_and_trims_overflow`, `test_tabs_payload_malformed_json_recovers_to_default_and_logs`, `test_tabs_payload_wrong_type_recovers_to_default_and_logs`

### CLI / Viewer workspace propagation

- `brain_ds/ui/cli.py`: `--root <path>` flag resolves `WorkspaceContext` and threads through to `render_graph_file`
- `brain_ds/ui/viewer.py`: `render_graph_file`/`render_graph_data` pass `workspace` kwarg to `build_render_context`
- `build_render_context` signature: `(graph, workspace: WorkspaceContext | None = None)` — OQ-C fallback when `None`
- Cross-language sync: `brain_ds/ui/src/contract_version.ts` mirrors `CONTRACT_VERSION = "1.0.0"`; enforced by `test_contract_version_sync.py` regex test

### Test evidence

Final full suite: **602 passed, 4 skipped** (`uv run python -m unittest discover -s tests`).

## Delivery Strategy

**Feature-branch-chain** with two slices plus remediation:

| Slice | Description | Status |
|-------|-------------|--------|
| PR 1 (RED/infrastructure) | Types, constants, TS mirror, CLI flag, all RED contract tests (failing as expected in chain) | ✅ Complete |
| PR 2 (GREEN/fixtures/verification) | GREEN helpers, injections, viewer/cli wiring, golden fixtures, verification suite | ✅ Complete |
| Warning remediation | Added dedicated `test_tab_model_opened_at_regex_is_locked_to_utc_seconds` source-backed regression for R08-A, plus R08-B/C/H history recovery evidence, final verify re-run | ✅ Complete |

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| render-context | Created (initial) | Copied delta spec — no existing main spec to merge against |

## Archive Contents

- `openspec/changes/archive/2026-05-20-backend-ui-contract/`
  - archive-report.md ✅ (this file)
  - proposal.md ✅
  - spec.md ✅
  - design.md ✅
  - tasks.md ✅ (22/22 tasks complete)
  - apply-progress.md ✅
  - verification-report.md ✅
  - exploration.md ✅

## Source of Truth Updated

- `openspec/specs/render-context/spec.md` — now reflects the v1.0.0 RENDER_CONTEXT contract

## PRs / Branches

- Feature branch: `feature/backend-ui-contract`
- PR #1 (RED/infrastructure): Infrastructure + failing contract tests
- PR #2 (GREEN): Implementation + golden fixtures + verification
- Final tracker PR: `feature/backend-ui-contract` → `main`
- Remediation commit(s): Warning closure for R08-A `openedAt` regex

## Live Bug Closure

- `popover.ts:77` — `node.score` previously `undefined`, now always numeric (R03-D). Closed by adding `score` as required per-node field. No TS edit required.

## Next Roadmap Step

**`workspace-shell-layout-migration`** — roadmap entry #2, Phase A. The 3-column → 5-column `graph_viewer.html` migration that consumes `contract_version 1.0.0` without further contract evolution.

## Risks Carried Forward

- None specific to this change. All acceptance signals confirmed:

1. ✅ `uv run python -m unittest discover -s tests` green (602 passed, 4 skipped)
2. ✅ `tests/test_viewer.py` and `tests/test_graph_contract.py` unchanged — green
3. ✅ `RENDER_CONTEXT.contract_version = "1.0.0"` pinned by literal test
4. ✅ `RENDER_CONTEXT.meta.workspace` present with 4 sub-fields
5. ✅ Every node has `score` (float), `updated_at` (locked ISO), `neighbor_count` (int)
6. ✅ `popover.ts:77` bug closed — score no longer `undefined`
7. ✅ Downstream changes can start against `contract_version 1.0.0` without further evolution

## SDD Cycle Complete

The change `backend-ui-contract` has been fully planned, implemented, verified (clean PASS), and archived.
Ready for the next change: `workspace-shell-layout-migration`.
