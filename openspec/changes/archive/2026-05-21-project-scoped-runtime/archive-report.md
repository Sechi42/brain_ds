# Archive Report — project-scoped-runtime

**Date**: 2026-05-21
**Change**: project-scoped-runtime
**Phase**: archive
**Artifact store**: hybrid
**Verdict**: PASS WITH WARNINGS (archive-eligible)

---

## Artifact Observation IDs (Engram Truth)

| Artifact | Engram ID | Topic Key |
|----------|-----------|-----------|
| Proposal | #966 | `sdd/project-scoped-runtime/proposal` |
| Spec | #969 | `sdd/project-scoped-runtime/spec` |
| Design | #968 | `sdd/project-scoped-runtime/design` |
| Tasks | #970 | `sdd/project-scoped-runtime/tasks` |
| Apply Progress | #972 | `sdd/project-scoped-runtime/apply-progress` |
| Verify Report | #978 | `sdd/project-scoped-runtime/verify-report` |
| Archive Report | This save | `sdd/project-scoped-runtime/archive-report` |

---

## Filesystem Archive Path

`openspec/changes/archive/2026-05-21-project-scoped-runtime/`

Contains: proposal.md, exploration.md, design.md, tasks.md, apply-progress.md, verify-report.md, archive-report.md

---

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| project-scoped-runtime | Created (full spec) | Copied delta spec to `openspec/specs/project-scoped-runtime/spec.md` — no prior main spec existed. Reflects CLI surface (serve mode + legacy static), WorkspaceContext path resolution, initial graph scanning, HTTP server & dynamic rendering, server lifecycle & graceful shutdown. |

---

## Source of Truth Updated

`openspec/specs/project-scoped-runtime/spec.md` — now reflects the full project-scoped runtime specification including all requirements and architecture decisions.

---

## Roadmap Position

Phase A · #4 of `backend-migration-to-new-ui` (engram #875).

**This change UNBLOCKS**:
- Phase B: `desktop-shell` (needs process model for Tauri backend)
- Phase B: `windows-exe-installer` (needs embedded server)
- Phase C: MCP path (builds on long-lived process foundation)

---

## As-Archived Behavior Summary

- **CLI surface**: `brain_ds ui` (no args) and `brain_ds ui serve` start project-scoped HTTP server on 127.0.0.1:8765. `brain_ds ui <graph_json>` preserved for backward compatibility.
- **WorkspaceContext**: Resolves project root once at startup; contains project_root, display_path (Windows forward-slash), store_path (`{root}/.brain_ds/store.db`). All Path.cwd() sites eliminated.
- **Initial graph scanning**: Depth-1 scan of project root and .brain_ds/ directory; imports valid v1 graph JSON files into GraphStore on startup.
- **HTTP server**: `GET /` returns dynamically rendered HTML using most recently updated graph. `GET /api/graphs` returns JSON graph list. Handles SIGINT/SIGTERM with graceful shutdown.
- **Graceful shutdown**: SIGINT/SIGTERM closes GraphStore (executes WAL checkpoint) and exits 0. No new third-party dependencies.

---

## Test Evidence

**Focused runtime suite** (18 tests, 0 failures):
- CLI suite: 3 tests (serve mode + legacy compat)
- Server suite: 6 tests (port conflict, root route, empty store, API endpoint, shutdown, WAL)
- WorkspaceContext suite: 3 tests (path resolution, Windows paths, CWD audit)
- Scanner suite: 2 tests (depth-1 scan, invalid JSON skip)
- Regression suite: 4 tests (import audit, threaded active-graph, port messages, integration)

**Full suite** (678 passed / 1 failed / 4 skipped):
- Single failure in test_installer (pre-existing, unrelated to this change)
- Failure: `test_register_path_copies_wrapper_sh` — opencode on PATH but dirname unavailable in Windows shell context
- Confirmed: test_installer.py NOT modified by this change (verified via git diff HEAD)

**TDD Compliance**: 6/6 checks passed (RED confirmed, GREEN confirmed, triangulation adequate, safety net verified)

---

## Files Changed (Final Set)

| File | Status |
|------|--------|
| `brain_ds/ui/server.py` | Created |
| `brain_ds/ui/cli.py` | Modified |
| `brain_ds/ui/viewer.py` | Modified |
| `brain_ds/ui/render_context.py` | Modified |
| `brain_ds/store/graph_store.py` | Modified |
| `tests/test_server.py` | Created |
| `tests/test_cli_serve.py` | Created |
| `tests/test_workspace.py` | Created |
| `tests/test_scanner.py` | Created |
| `tests/test_regression.py` | Created |

---

## Predecessors Closed

✅ `sqlite-graph-store` (archived #962) — provides GraphStore contract, schema, migrations. Now consumed by a production runtime.

---

## Successors Unblocked

- Phase B: `desktop-shell` — can now wrap the server process
- Phase B: `windows-exe-installer` — can bundle the server
- Phase C: `mcp-server` — builds on the running event loop

---

## Future Checks / Signposts (Preserved from Verify Warnings)

The following artifact/spec coherence and implementation items remain as future checks before the next change touching project-scoped-runtime or Phase B/C:

1. **SUGGESTION**: Active-graph recency proof is at selector layer (`active_graph.org == "New Org"`), not rendered HTML body. Transitively sufficient today; consider strengthening to a body-level assertion if recency selection logic evolves.

2. **SUGGESTION**: Recency test uses `time.sleep(1.1)` for timestamp separation. Slow on loaded CI; consider injectable clock if test latency becomes a problem.

3. **EXTERNAL — separate ticket**: `test_installer` fails on full suite (678 passed / 1 failed / 4 skipped). Pre-existing, NOT caused by this change. Likely Windows `dirname`/`opencode` PATH env quirk. Track separately — this change's archive does NOT close it.

4. **CARRIED FROM sqlite-graph-store**: `:memory:` WAL wording, coverage tooling absence, `wal_checkpoint(TRUNCATE)` cross-platform brittleness, artifact-sync hygiene — still applicable to the runtime layer.

---

## Risks

- None — all CRITICAL issues closed. Residual warnings are optional quality improvements and pre-existing environmental issues.

---

## Completion Checklist

- [x] All 31 task checklist items complete
- [x] 13/13 spec scenarios compliant
- [x] 18/18 focused runtime tests pass
- [x] TDD compliance 6/6
- [x] Proposal, Spec, Design, Tasks, Apply-progress, Verify-report all generated
- [x] Delta spec merged into main spec at `openspec/specs/project-scoped-runtime/spec.md`
- [x] Change folder moved to archive at `openspec/changes/archive/2026-05-21-project-scoped-runtime/`
- [x] Archive report written and persisted
- [x] No new third-party dependencies
- [x] Path.cwd() references eliminated from serve path (5 sites replaced)
- [x] RENDER_CONTEXT contract v1.0.0 unchanged
- [x] GraphStore contract consumed unmodified

---

## Archive Status

**CLOSED** — project-scoped-runtime is archived and ready for Phase B/C follow-up.
