# Proposal: project-scoped-runtime

**Date**: 2026-05-21
**Change**: project-scoped-runtime
**Phase**: propose
**Roadmap**: backend-migration-to-new-ui — Phase A · #4 (engram #875)
**Exploration**: engram #965 / openspec/changes/project-scoped-runtime/exploration.md
**Predecessors**: backend-ui-contract (archived), workspace-shell-layout-migration (archived), sqlite-graph-store (archived)
**Artifact store**: hybrid (file + engram topic_key `sdd/project-scoped-runtime/proposal`)

---

## Intent

Convert `brain_ds ui` from a one-shot static HTML generator into a project-scoped runtime. A single command launched inside any project directory must (a) resolve the project root, (b) open the SQLite store at `{project-root}/.brain_ds/store.db`, (c) start a local HTTP server, and (d) serve the existing workspace-shell UI bound to the project's persisted graph(s). Backward compatibility with the static `brain_ds ui <graph_json>` flow is preserved for fixtures and CI.

This change is the keystone of Phase A: it lights up the persistence layer shipped in `sqlite-graph-store` (#3) by giving it a runtime owner, and it produces the executable surface that Phase B (`desktop-shell`, `windows-exe-installer`) will embed and Phase C (`mcp-server`, manual editing) will extend.

## Problem

- Today `brain_ds ui` requires an explicit `graph_json` path; there is no concept of "open this project."
- Five hardcoded `Path.cwd()` references (cli.py:67, 68, 98; viewer.py:113; render_context.py:171) leak working-directory assumptions into the render pipeline — incompatible with a desktop app launched from arbitrary directories.
- `GraphStore` (archived `sqlite-graph-store`) is fully functional but has **no consumer** — nothing in `brain_ds/ui/` opens `.brain_ds/store.db`.
- Phase B cannot ship without a process model for the backend (Tauri must spawn something and point a webview at it).
- Phase C MCP requires a long-lived process; staying in static-generator mode forces a rewrite later instead of an additive upgrade.
- No project-scanning code exists today — there is no MVP definition of "what graphs belong to this project."

## Scope (In)

### CLI surface
- `brain_ds ui` (no `graph_json` argument) → enters **project-scoped serve mode**.
- `brain_ds ui serve` → explicit subcommand alias for the same behavior, for discoverability.
- `brain_ds ui <graph_json>` → **unchanged**. Static generator stays bit-for-bit backward compatible.
- New flags on serve mode:
  - `--port` (default `8765`)
  - `--project-root` (default: resolved CWD; resolved **once at startup** and threaded through every component — never re-read).
  - `--open` (open the default browser to `http://localhost:{port}/` after bind).
- Flags shared with the static generator (`--simple`, `--force`) are accepted only in static mode.

### Storage convention
- `{project-root}/.brain_ds/store.db` — hidden workspace directory created on first launch if missing.
- Permissions: directory `0o755`, DB file inherits OS default. Hidden-folder semantics on Windows (no attrib flag required; dot-prefix is enough for the tools we target).
- The store contract from `sqlite-graph-store` is consumed **unmodified**. No schema additions, no migration changes, no new public methods.

### New code
- `brain_ds/ui/server.py` — `http.server.HTTPServer`/`BaseHTTPRequestHandler` subclass + lifecycle (bind, serve, SIGINT/SIGTERM → `GraphStore.close()`).
- `WorkspaceContext` (or equivalent dataclass) — single source of truth for `{project_root, display_path, store_path}`; constructed once in `main()` and passed by reference everywhere the render pipeline needs it.

### Modified code
- `brain_ds/ui/cli.py` — argparse wiring for the optional `graph_json` arg and the new `serve` subcommand; project-root flag plumbing.
- `brain_ds/ui/viewer.py` — accept an injected `WorkspaceContext` for output-path resolution; remove the `Path.cwd() / "graph-output.html"` fallback in favor of explicit threading.
- `brain_ds/ui/render_context.py` — accept the resolved workspace root from `WorkspaceContext` instead of calling `Path.cwd()` at line 171.
- `brain_ds/ui/__init__.py` — export the new `serve()` entry point if needed for tests.

### Server behavior (Phase A scope)
1. Resolve project root (CLI flag or CWD), assert it exists and is a directory.
2. Ensure `{project-root}/.brain_ds/` exists.
3. Open `{project-root}/.brain_ds/store.db` via `GraphStore(path)` (WAL, FK, single connection).
4. **Project-scan MVP**: enumerate `*.json` files at `{project-root}/` and `{project-root}/.brain_ds/` whose contents parse as a v1 graph schema. Import any whose path is not already represented in `store.list_graphs()`. Dedup by `imported_from`.
5. Select **one active graph** = most recent entry from `store.list_graphs()` (by `updated_at`, falling back to `created_at`).
6. Bind `http.server.HTTPServer` on `127.0.0.1:{port}` (loopback only — not `0.0.0.0`; desktop-local is the threat model).
7. Routes:
   - `GET /` — load active graph from SQLite → `build_render_context(graph, workspace)` → `render_interactive_html(context)` → 200 text/html.
   - `GET /api/graphs` — `store.list_graphs()` → 200 application/json. (Stub for multi-tab swap; not the headline feature in Phase A.)
   - Anything else → 404.
8. SIGINT/SIGTERM (and Windows `CTRL_C_EVENT`) → `store.close()` (which runs `wal_checkpoint(TRUNCATE)`) → exit 0.

### Tests (new files; strict TDD red→green per acceptance signal)
- `tests/test_ui_server_startup.py` — bind succeeds, returns 200 on `/`, request body contains `RENDER_CONTEXT`.
- `tests/test_ui_server_port_conflict.py` — bind fails with a clear error message when the port is in use.
- `tests/test_ui_server_project_root.py` — `--project-root` resolution, default-CWD resolution, missing-directory error.
- `tests/test_ui_server_store_integration.py` — server reads from a `:memory:`-or-tempfile `GraphStore`, dynamic render hits the store, no CWD writes.
- `tests/test_ui_server_shutdown.py` — SIGINT path closes store, WAL checkpoint observable as best-effort assertion (see Risk 9 — soft-assert only).
- `tests/test_ui_server_windows_paths.py` — `WorkspaceContext.displayPath` stays forward-slash on Windows-style inputs (POSIX display rule from R02).
- `tests/test_ui_project_scan.py` — known graphs skipped, unknown graphs imported, malformed JSON files ignored without crash.

## Scope (Out / Non-Goals)

Explicitly **NOT** in this change. These belong to Phase B/C and must not bleed in:

- **File watcher / auto-reload** — no `watchdog`, no inotify, no polling. Browser refresh re-renders dynamically; that is the entire "live update" story for Phase A.
- **WebSocket / SSE** — Phase C MCP territory.
- **MCP server / tools** — Phase C (`mcp-server` change).
- **`/api/*` beyond `/api/graphs`** — `get_node`, `update_node`, `add_edge` etc. are Phase C.
- **Multi-user auth / CORS** — loopback-only bind makes this moot for Phase A.
- **Hot graph upload via HTTP** — no `POST /api/import`. Graphs land via the scan + SQLite path.
- **Multi-tab "active graph" swap UI** — schema exists (R08 TabModel), but the headline behavior in Phase A is single active graph at startup. A latent swap-by-`graph_id` test is allowed; UI affordance is not.
- **Project scanning beyond MVP** — no recursive walk, no `.gitignore` honoring, no metadata heuristics, no `pyproject.toml`-aware project detection.
- **GraphStore schema changes** — contract frozen by `sqlite-graph-store` archive (#962).
- **Template / RENDER_CONTEXT contract changes** — contract_version stays 1.0.0; spec tests from #1 must continue to pass untouched.
- **Packaging / installer / Tauri wiring** — Phase B.

## Approach

**Approach B from exploration #965** — Python stdlib `http.server` with per-request dynamic rendering.

Rationale (in order of weight):

1. **Zero new dependencies.** `http.server` ships with CPython. Consistent with the sqlite3-only constraint adopted in `sqlite-graph-store`. Keeps the `.exe` bundle minimal and PyInstaller-friendly.
2. **Phase C upgrade path.** A running event loop with route registration is the natural seed for an MCP WebSocket server. We add routes; we do not rewrite the entry point.
3. **Tauri-ready.** The server is a process the Rust shell can spawn and address; port is the only handshake.
4. **Full reuse of the existing render pipeline.** `build_render_context()` and `render_interactive_html()` are called per request on the SQLite-loaded `Graph`. The template contract is untouched. Sections 1 and 2 of the roadmap stay green by construction.
5. **Backward compatibility is cheap.** The static-generator path is the same function call with a different writer (file vs HTTP response). Two thin wrappers, one shared core.

Approaches A (static + watcher) and C (Flask/FastAPI) are rejected per #965 — A has no Phase C path, C adds dependency weight for one route.

## Architecture Decisions

- **ADR-1**: Loopback-only bind (`127.0.0.1`). Desktop-local threat model; revisit when remote MCP arrives in Phase C.
- **ADR-2**: One `GraphStore` connection for the server lifetime. WAL allows concurrent readers. Single-writer contract still holds because Phase A has no writes.
- **ADR-3**: `WorkspaceContext` resolved **once** in `main()`. No component re-reads CWD. All five `Path.cwd()` callsites are replaced with explicit threading.
- **ADR-4**: Active-graph selection = most recent from `list_graphs()`. Multi-tab swap deferred to Phase B/C UI work.
- **ADR-5**: Project-scan MVP = depth-1 scan of project root + `.brain_ds/`. Anything more sophisticated is Phase C.
- **ADR-6**: Static-generator path (`brain_ds ui <graph_json>`) preserved as a thin wrapper around the same render pipeline — no removal, no deprecation warning in Phase A.

## Risks & Mitigations

Propagating the 9 risks from exploration #965:

1. **CWD-assumption audit (MEDIUM)** — 5 hardcoded `Path.cwd()` sites. *Mitigation*: every callsite replaced with `WorkspaceContext`-threaded value; a regression test asserts no `Path.cwd()` call occurs inside `viewer.py` / `render_context.py` during a serve request.
2. **Multi-graph "active graph" selection (LOW)** — R08 schema permits multiple graphs; UI has never been exercised with more than one. *Mitigation*: ADR-4 + a test fixture with 2 graphs verifying the most-recent one renders.
3. **Long-lived store connection lifecycle (MEDIUM)** — `GraphStore` was designed for short-lived ops. *Mitigation*: explicit `close()` on signal; readers only in Phase A; signal handler integration tested.
4. **Port conflicts (LOW)** — 8765 may be busy. *Mitigation*: clear error message, exit 1, no auto-retry. Document the `--port` flag in the help text.
5. **No project-scanning code exists (HIGH)** — green-field. *Mitigation*: MVP scope frozen in ADR-5; everything more elaborate is explicitly deferred and tested as out-of-scope.
6. **Windows path handling for `WorkspaceContext.displayPath` (LOW)** — R02 requires POSIX forward-slash display. *Mitigation*: dedicated Windows-path test (`test_ui_server_windows_paths.py`) before implementation.
7. **PyInstaller resource resolution (LOW)** — template assets via `importlib.resources`. *Mitigation*: out of scope here; flag for `windows-exe-installer` to verify with `--add-data`.
8. **Phase C MCP WebSocket swap (MEDIUM)** — `http.server` + threading is awkward for WS. *Mitigation*: keep the request handler thin and the route table explicit; the WS upgrade may replace the server class without touching handlers.
9. **Sqlite-graph-store warning signposts** — honor the four from archive #962:
   - `:memory:` WAL wording — server tests should use file-backed temp DBs to avoid the `journal_mode=memory` confusion.
   - Coverage tooling unavailable — accepted as-is; do not add new dev deps.
   - `wal_checkpoint(TRUNCATE)` cross-platform brittleness — shutdown test soft-asserts (existence/idempotency), not exact checkpoint size.
   - Artifact sync hygiene — design/spec/tasks/apply/verify references must stay in lockstep through this phase.

## TDD Acceptance Posture

`strict_tdd: true` is active (`sdd-init/brain_ds` #156). Every deliverable lands red→green:

1. Failing test committed **before** any implementation for each public surface (`server.serve()`, `server.handle_root()`, `server.handle_list_graphs()`, `WorkspaceContext.resolve()`, `project_scan()`).
2. `uv run python -m unittest discover -s tests` baseline **602 passed, 4 skipped, 0 failed** (from sqlite-graph-store final verify) must not regress. New tests strictly add to the green count.
3. No implementation file in `brain_ds/ui/server.py` may land in a commit that does not also include or follow a failing-test commit referencing the same surface.
4. No new third-party dependency in `pyproject.toml` / `uv.lock`.

## Acceptance Signals

1. `uv run python -m unittest discover -s tests` green; new server / scan / context tests included.
2. Every public function in `server.py` and `WorkspaceContext` has a failing test before the implementation commit (verifiable in git history).
3. `brain_ds ui` (no args) in a fresh project directory: creates `.brain_ds/store.db`, prints the local URL, returns 200 on `GET /` with a body containing `RENDER_CONTEXT`.
4. `brain_ds ui <graph_json>` produces the same HTML it did before this change (golden-fixture parity).
5. SIGINT during serve closes the store and exits 0; no orphaned `-wal`/`-shm` files in the happy path.
6. All 5 `Path.cwd()` references identified in #965 are gone from `cli.py`, `viewer.py`, `render_context.py`. Grep proves this.
7. RENDER_CONTEXT contract (1.0.0) unchanged — existing contract tests pass untouched.
8. No new third-party dependency.
9. Windows-style project root produces forward-slash `WorkspaceContext.displayPath`.

## Open Questions for Spec Phase

- **OQ-1**: Should `/api/graphs` already return the R08 TabModel shape, or a minimal `[{id, label}]` list? (Minimal is cheaper; TabModel is forward-aligned.)
- **OQ-2**: Active-graph tiebreaker when `updated_at` is equal — alphabetical `label` or insertion order? (Test determinism matters.)
- **OQ-3**: Project-scan import errors — log-and-skip, or fail-fast? Recommendation: log-and-skip with a counted summary at startup.
- **OQ-4**: `--open` on Windows — `webbrowser.open()` is fine, but should we suppress it when running under tests? Probably yes via an env var override.
- **OQ-5**: Where does the resolved `WorkspaceContext` live — module-level singleton in `server.py`, or threaded through every call? Recommendation: threaded; singletons fight tests.
- **OQ-6**: Should `serve` accept stdin graph JSON like the static path does? Recommendation: no — serve is project-scoped by definition.

## Review Workload Forecast (preliminary)

- `brain_ds/ui/server.py` ~280 lines
- `brain_ds/ui/cli.py` modifications ~80 lines
- `brain_ds/ui/viewer.py` + `render_context.py` CWD replacements ~40 lines
- `WorkspaceContext` (new) ~60 lines
- Tests ~520 lines across 7 files

Total estimate **~980 lines** — well above the 400-line budget. `sdd-tasks` should flag `Chained PRs recommended: Yes`, `400-line budget risk: High` and propose a chain along these slices:

1. `WorkspaceContext` + CWD-replacement refactor + tests (no behavior change yet).
2. `server.py` skeleton + `GET /` + startup/shutdown tests.
3. Project-scan MVP + import tests.
4. `cli.py` wiring (`serve` subcommand + no-arg fallback) + integration tests.
5. `/api/graphs` route + multi-graph fixture tests.

## Engram Trail

- Exploration: engram #965
- Predecessor archive: engram #962 (sqlite-graph-store)
- Roadmap: engram #875 (Phase A · #4)
- Proposal: `openspec/changes/project-scoped-runtime/proposal.md` + topic_key `sdd/project-scoped-runtime/proposal`
- Next phases: `sdd-spec` and `sdd-design` (parallel — both read this proposal).
