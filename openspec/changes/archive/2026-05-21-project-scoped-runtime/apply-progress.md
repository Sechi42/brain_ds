# Apply Progress: project-scoped-runtime

**Change**: project-scoped-runtime  
**Mode**: Strict TDD  
**PR Boundary**: PR5 remediation only (verify-report #978 closure), stacked-to-main

## Reconciliation Table

| Type | Mapping |
|---|---|
| Requirement/scenario → behavior → test | Port conflict emits stable user-facing error and exits `1` → `run_server()` now prints `Error: port {port} is already in use` to `stderr` before `SystemExit(1)` → `tests/test_server.py::test_run_server_port_conflict_reports_clear_error_and_exits_1` |
| Requirement/scenario → behavior → test | Active graph recency is proven with runtime metadata ordering and threaded HTTP serve path → file-backed `GraphStore` imports old graph then newer graph (time-separated writes), `_active_graph_payload()` selects newest graph (`New Org`) and `GET /` still returns contract payload → `tests/test_regression.py::test_threaded_runtime_serves_active_graph_with_render_context_contract` |
| Requirement/scenario → behavior → test | Graceful shutdown cleanup is proven with file-backed store and sidecar-handle release check → SIGINT handler closes store, exits `0`, and any WAL/SHM sidecars can be renamed/deleted without lock failures → `tests/test_server.py::test_sigint_handler_closes_file_backed_store_and_releases_wal_shm_handles` |
| Design coherence → artifact sync | Design file-change table updated to reflect implemented files from PR1–PR5 including `graph_store.py`, `test_scanner.py`, and `test_regression.py` → `openspec/changes/project-scoped-runtime/design.md` |

## Completed Tasks (cumulative)

- [x] 1.1–1.8 (PR1)
- [x] 2.1–2.10 (PR2)
- [x] 3.1–3.7 (PR3)
- [x] 4.1–4.6 (PR4)
- [x] PR5 remediation: verify #978 CRITICAL + WARNING findings closed with focused runtime evidence and design sync

## Files Changed (this slice)

- `brain_ds/ui/server.py` (modified)
- `tests/test_server.py` (modified)
- `tests/test_regression.py` (modified)
- `openspec/changes/project-scoped-runtime/design.md` (modified)
- `openspec/changes/project-scoped-runtime/apply-progress.md` (created)

## TDD Cycle Evidence (PR5 remediation)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Port-conflict message + exit 1 | `tests/test_server.py` | Unit/Integration | ✅ `tests.test_server tests.test_regression` baseline (8/8) | ✅ Added failing stderr assertion first | ✅ Passed after server error-message implementation | ✅ Exit code and stderr content asserted | ➖ None needed |
| Active-graph recency proof | `tests/test_regression.py` | Integration | ✅ same baseline | ✅ Added failing newest-graph assertion first | ✅ Passed with deterministic timestamp-separated imports | ✅ Verified selector result + threaded `GET /` contract path | ✅ Test hardened with cleanup-safe `try/finally` |
| Shutdown cleanup proof | `tests/test_server.py` | Integration | ✅ same baseline | ✅ Added file-backed shutdown sidecar-release assertion first | ✅ Passed after cleanup assertion refinement | ✅ Covers store close + process exit + handle release semantics | ➖ None needed |
| Design drift sync | `design.md` | Docs | N/A | ✅ Drift identified in verify report | ✅ File-change table updated to actual implementation set | ➖ Single documentation path | ➖ None needed |

## Tests Run (this slice)

- `uv run python -m unittest tests.test_server tests.test_regression` (RED and GREEN cycles)
- `uv run python -m unittest tests.test_cli_serve tests.test_server tests.test_scanner tests.test_regression` (focused runtime regression: 14 passed)
- `uv run python -m unittest discover -s tests` (full suite: 679 passed, 4 skipped)

## Deviations from Design

- None in runtime behavior.
- Design artifact now synchronized to actual implemented file set.

## Issues Found

- During remediation, active-graph recency test exposed non-determinism when imports share the same timestamp window; test now uses time-separated writes for stable recency proof.

## Remaining Tasks

- [x] None. PR5 remediation scope complete and ready for re-verify.
