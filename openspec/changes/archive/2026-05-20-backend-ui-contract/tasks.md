# Tasks: backend-ui-contract

**Date**: 2026-05-20 | **TDD**: strict | **Test runner**: `uv run python -m unittest discover -s tests`

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 410–635 (production: ~98–155; tests+fixtures: ~310–480) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 (feature-branch-chain; PR 2 targets PR 1 branch) |
| Delivery strategy | ask-on-risk |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base | Notes |
|------|------|-----------|------|-------|
| 1 | Types, constants, TS mirror, CLI flag, all RED contract tests | PR 1 | `feature/backend-ui-contract` | Tests WILL fail — expected in feature-branch-chain |
| 2 | GREEN helpers, injections, viewer/cli wiring, golden fixtures, verification | PR 2 | PR 1 branch | Makes all tests pass; <200 prod lines |
| — | Final integration | Tracker PR | `feature/backend-ui-contract` → main | Both child PRs merged; acceptance signals confirmed |

**Alternative**: single PR with `size:exception` (test files are reviewer-reasonable — mostly declarative assertions, low review complexity).

---

## Phase 1: Infrastructure (scaffold only, no behavior)

- [x] 1.1 Add `WorkspaceContext` dataclass + `CONTRACT_VERSION = "1.0.0"` constant to `brain_ds/ui/render_context.py`
- [x] 1.2 Create `brain_ds/ui/src/contract_version.ts` — single export: `export const CONTRACT_VERSION = "1.0.0";`
- [x] 1.3 Add `--root <path>` optional flag to `ui` subparser in `brain_ds/ui/cli.py` (parse only, no wiring yet)

## Phase 2: RED — Failing Contract Tests (write before production)

- [x] 2.1 Create `tests/test_render_context_contract.py` — R01 tests: `test_contract_version_is_one_zero_zero` (literal equality, root-level presence)
- [x] 2.2 R02 tests: `test_meta_workspace_present_and_well_formed`, depth-zero, depth-one-only, POSIX-slashes-on-Windows
- [x] 2.3 R03 tests: `test_every_node_has_score`, `test_node_score_is_max_of_incident_edge_scores`, `test_isolated_node_score_is_zero`, `test_node_score_full_float_precision`, `test_node_score_never_undefined`
- [x] 2.4 R04 tests: `test_every_node_has_updated_at`, `test_node_updated_at_is_max_incident_evidence_timestamp`, `test_isolated_node_updated_at_falls_back_to_meta_generated_at`, `test_updated_at_format_matches_locked_pattern`
- [x] 2.5 R05 tests: `test_every_node_has_neighbor_count`, `test_neighbor_count_isolated_is_zero`, `test_neighbor_count_matches_adjacency`
- [x] 2.6 Create `tests/test_contract_version_sync.py` — regex-extract `/CONTRACT_VERSION\s*=\s*"([^"]+)"/` from TS file; assert equality with Python `CONTRACT_VERSION`

## Phase 3: GREEN — Production Implementation

- [x] 3.1 Implement `_compute_node_score` (max incident edge weight, isolated→0.0) and `_compute_neighbor_count` (adjacency list length, absent→0); inject both per-node in `build_render_context`
- [x] 3.2 Implement `_compute_node_updated_at` (max incident evidence timestamps, fallback to `meta.generated_at`); inject per-node
- [x] 3.3 Implement `_compute_workspace_meta` with OQ-C fallback (`workspace is None`→log warning→synthesize `project="default"`); inject `meta.workspace` into returned dict
- [x] 3.4 Inject `"contract_version": CONTRACT_VERSION` at root level of returned dict
- [x] 3.5 Modify `build_render_context` signature to `(graph, workspace: WorkspaceContext | None = None)` — all 10 existing call sites in `tests/test_viewer.py` + `test_theme.py` + `test_smoke.py` stay compatible
- [x] 3.6 Thread `workspace` kwarg through `render_graph_file` / `render_graph_data` in `brain_ds/ui/viewer.py` (optional, defaults to `None`)
- [x] 3.7 Wire `WorkspaceContext` resolution in `brain_ds/ui/cli.py` — resolve `--root` vs cwd, construct `WorkspaceContext`, pass to `render_graph_file` via `_run_ui`

## Phase 4: Golden Fixtures

- [x] 4.1 Create 7 minimal graph input fixtures: `tests/fixtures/graph_inputs/{actor,data,process,problem,risk,metric,solution}.json` (2-4 nodes each; one edge for non-isolated nodes)
- [x] 4.2 Generate 7 golden `RENDER_CONTEXT` outputs via `update_golden=True` helper; save to `tests/fixtures/render_context/<supertype>.json`
- [x] 4.3 Create `tests/test_render_context_golden.py` — 7 test methods, one per supertype, sorted-key deep-equal against golden (accidental drift→failure)
- [x] 4.4 Add R08 schema test: `test_tab_model_schema_fields_documented` — static assertion that locked `TabModel` has exactly 6 fields

## Phase 5: Verification

- [x] 5.1 Run `uv run python -m unittest discover -s tests` — confirm all new + existing tests green
- [x] 5.2 Verify acceptance signals from spec: contract_version=1.0.0, meta.workspace present, every node has score/updated_at/neighbor_count, popover.ts:77 bug closed (R03-D), test_viewer.py and test_graph_contract.py unchanged+green
