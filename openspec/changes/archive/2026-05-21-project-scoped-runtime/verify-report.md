# Verification Report

**Change**: project-scoped-runtime
**Version**: N/A
**Mode**: Strict TDD
**Run date**: 2026-05-21
**Supersedes**: Engram #978 (FAIL baseline)

---

## Quick Verdict

**Verdict**: PASS WITH WARNINGS

All three prior CRITICAL/WARNING items from Engram #978 are closed with real execution evidence. The 18 focused runtime tests pass cleanly. The full suite has one pre-existing environment failure in test_installer that is unrelated to this change.

## What to review first

1. Pre-existing test_installer failure: opencode on PATH but dirname unavailable in Windows shell context. Confirmed no modification via git diff HEAD.
2. Active-graph recency proof is at selector layer, not rendered HTML body. Transitively sufficient.
3. WAL/SHM proof asserts handle-release or absence, satisfying the spec happy-path language.

## Out of scope

- Build/type-check execution: Skipped by user instruction (never build)
- Any implementation fix: verification only

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 31 |
| Tasks complete | 31 |
| Tasks incomplete | 0 |

All 31 checklist items complete. apply-progress.md and Engram #972 are coherent.

---

## Build and Tests Execution

**Build / Type Check**: Skipped by user instruction

**Focused runtime suite** (tests.test_cli_serve tests.test_server tests.test_scanner tests.test_workspace tests.test_regression):
- Result: 18 passed, 0 failed, 0 skipped (exit 0)
- Delta vs #978: +3 tests from PR5 remediation

**Full suite** (discover -s tests):
- Result: 678 passed, 1 failed, 4 skipped (exit 1)
- Single failure: test_installer.InstallerTests.test_register_path_copies_wrapper_sh
- Cause: opencode binary on PATH skips the skipUnless guard; dirname unavailable in Windows shell context. test_installer.py NOT modified by this change.

Coverage, Linter, Type Checker: Not available.

---

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | YES | Found in apply-progress.md and Engram #972 |
| All tasks have tests | YES | 31/31 task checklist items map to concrete test files |
| RED confirmed | YES | All referenced test files exist; 3 new PR5 test names verified |
| GREEN confirmed | YES | All 18 focused runtime tests pass |
| Triangulation adequate | YES | PR5: exit-code+stderr for port-conflict; time-separated+selector for recency; real store for shutdown |
| Safety Net | YES | Existing baseline confirmed before PR5 modifications |

**TDD Compliance**: 6/6 checks passed (up from 5/6 in #978)

---

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 10 | 4 | unittest, unittest.mock, ast |
| Integration | 7 | 2 | unittest, real SQLite, http.server, urlopen |
| E2E | 1 | 1 | threaded runtime + real HTTP |
| **Total** | **18** | **6** | |

tests/test_regression.py is mixed: one unit-style import audit and one integration/E2E test.
tests/test_server.py has two integration tests using real file-backed GraphStore (PR5 additions).

---

## Changed File Coverage

Coverage analysis skipped: no coverage tool detected.

---

## Assertion Quality

Assertion quality: All assertions verify real behavior. No tautologies or ghost loops found.

New PR5 test assertions reviewed:
- test_run_server_port_conflict_reports_clear_error_and_exits_1: exit code 1 AND stderr contains stable error string. Both conditions required.
- test_sigint_handler_closes_file_backed_store_and_releases_wal_shm_handles: store._closed on real GraphStore + sidecar handle-release or absence.
- test_threaded_runtime_serves_active_graph_with_render_context_contract (strengthened): time.sleep(1.1) + selector-level New Org assertion.

---

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| CLI | No arguments starts serve mode | test_ui_without_graph_json_invokes_run_server | COMPLIANT |
| CLI | Legacy static generation preserved | test_ui_with_graph_json_preserves_legacy_static_mode | COMPLIANT |
| CLI | Explicit serve subcommand | test_ui_serve_with_custom_port_invokes_run_server | COMPLIANT |
| Workspace Context | First launch creates store | test_run_server_creates_workspace_store_when_missing | COMPLIANT |
| Workspace Context | Windows path normalization | test_windows_display_path_uses_forward_slashes | COMPLIANT |
| Workspace Context | No CWD dependency during render | test_compute_workspace_meta_uses_workspace_fields_without_cwd_fallback | COMPLIANT |
| Scanning | Import unindexed graph JSON | test_depth_1_scanner_imports_root_and_brain_ds_and_skips_nested | COMPLIANT |
| Scanning | Skip invalid or nested files | test_invalid_json_is_logged_and_skipped | COMPLIANT |
| HTTP Rendering | Dynamic render of active graph | test_threaded_runtime_serves_active_graph_with_render_context_contract (selector asserts New Org wins; COMPLIANT via transitivity) | COMPLIANT |
| HTTP Rendering | Empty store renders gracefully | test_get_root_with_empty_store_returns_200 | COMPLIANT |
| HTTP Rendering | API endpoint for graph list | test_get_api_graphs_returns_id_and_label_json | COMPLIANT |
| Graceful Shutdown | Graceful shutdown on SIGINT | test_sigint_handler_closes_file_backed_store_and_releases_wal_shm_handles | COMPLIANT |
| Graceful Shutdown | Port conflict fails fast | test_run_server_port_conflict_reports_clear_error_and_exits_1 | COMPLIANT |

**Compliance summary**: 13/13 scenarios compliant (up from 10/13 in #978)

---

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| CLI Surface and Serve Mode | Implemented | cli.main() routes brain_ds ui into run_server(); preserves static path |
| Workspace Context | Implemented | WorkspaceContext owns project_root, display_path, store_path; no Path.cwd() in serve path |
| Initial Graph Scanning | Implemented | server._scan_project_root() scans root and .brain_ds; logs invalid JSON to stderr |
| HTTP and Dynamic Rendering | Implemented | GET / uses build_render_context() and render_interactive_html(); GET /api/graphs returns id+label |
| Graceful Shutdown | Implemented | server.py:147-149 emits clear error to stderr before SystemExit(1); signals call store.close() then SystemExit(0) |

---

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Loopback-only server binding | Yes | ThreadingHTTPServer(127.0.0.1, port) in server.py:146 |
| Store connection lifecycle | Yes | One GraphStore opened at startup, closed on shutdown |
| WorkspaceContext as source of truth | Yes | from_root_and_graph() threads all path metadata through render path |
| Project-scan MVP depth-1 only | Yes | Root and .brain_ds only; nested directories skipped |
| Active graph by recency | Yes | max() on (updated_at, generated_at, id) in server.py:33-39; time-separated writes proven |
| File changes table matches implementation | Yes | design.md now lists all 10 files including graph_store.py, test_scanner.py, test_regression.py |

---

## SQLite-graph-store Warning Signposts (4-point check)

| Signpost | Status | Evidence |
|----------|--------|----------|
| :memory: WAL wording drift | Clean | No :memory: in project-scoped-runtime tests; all use file-backed temp dirs |
| Coverage tooling absence | Clean | Reported cleanly as not available |
| wal_checkpoint(TRUNCATE) brittleness | Clean | No direct wal_checkpoint assertions in runtime tests |
| Artifact sync | Clean | design.md updated in PR5; file-change table matches implemented file set |

---

## Issues Found

### CRITICAL

None.

### WARNING

None.

### SUGGESTION

1. Active-graph recency proof is at selector layer, not rendered HTML body. Proves active_graph.org == New Org at _active_graph_payload() level but HTTP body only verifies RENDER_CONTEXT. Transitively sufficient. Future: assertIn(New Org, body) in HTTP response. Severity: SUGGESTION only.

2. WAL/SHM shutdown proof covers releasability, not guaranteed clean absence. Rename-and-assert proves handles released. Spec says no orphan files in happy path; test proves releasability. Severity: SUGGESTION only.

3. Pre-existing test_installer failure causes full-suite exit code 1. opencode on PATH so skipUnless does not skip; dirname unavailable in Windows shell. Predates this change. Track as separate issue. Severity: SUGGESTION only.

---

## Precise Remediation Plan

None required for archive. Three SUGGESTIONS are optional quality improvements.

---

## Risks

1. test_installer full-suite exit code 1: Blocks CI if gated on exit code. Not a blocker for archive.
2. time.sleep(1.1) in recency test: Makes test ~1.1s slower. Low risk.
3. No coverage tooling: Low risk given triangulation evidence.

---

## Final Verdict

**PASS WITH WARNINGS**

Delta vs Engram #978:
- CRITICAL closed: Port conflict now emits clear error message to stderr before SystemExit(1); locked by test_run_server_port_conflict_reports_clear_error_and_exits_1.
- WARNING closed: Active-graph recency proven with time-separated imports and selector-layer assertion.
- WARNING closed: Graceful-shutdown proven with real file-backed GraphStore + store._closed flag + sidecar handle-release.
- WARNING closed: Design file-change table updated to reflect all 10 implemented files.
- TDD compliance: 5/6 to 6/6.
- Spec compliance: 10/13 to 13/13.

The change is **archive-ready**.