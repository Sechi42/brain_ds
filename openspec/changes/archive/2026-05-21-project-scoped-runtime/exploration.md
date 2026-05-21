## Exploration: project-scoped-runtime

**Date**: 2026-05-21
**Change**: `project-scoped-runtime`
**Phase**: explore
**Roadmap**: backend-migration-to-new-ui — Phase A · #4 (observation #875)
**Predecessors**: backend-ui-contract ✅ archived, workspace-shell-layout-migration ✅ archived, sqlite-graph-store ✅ archived
**Artifact store**: hybrid (file + Engram topic_key `sdd/project-scoped-runtime/explore`)

---

### Current State

#### CLI surface (`brain_ds/ui/cli.py`)
- Single entry point: `brain_ds = "brain_ds.ui.__main__:main"` (pyproject.toml)
- Two subcommands: `ui` and `validate`
- `brain_ds ui <graph_json> [--root] [--output] [--open] [--simple] [--force]`
  - `graph_json` is REQUIRED — path to a graph JSON file (or `-` for stdin)
  - `--root` sets workspace root (optional; defaults to `Path.cwd()`)
  - Output: standalone self-contained HTML file (static generator, NOT a server)
- **No `serve` command exists.** No HTTP server. No persistent runtime.
- `--root` flag is the only project-root mechanism; it's optional and not validated

#### Graph pipeline
```
graph JSON file → Graph.from_v1() → build_render_context() → render_interactive_html() → HTML file
```
- Zero persistence between parse and render — the JSON file is the ONLY representation
- No project scanning, no ingestion pipeline, no runtime cache
- Graph construction (elicit/map) lives in OpenCode commands (`commands/`, `.opencode/skills/`), NOT in the Python codebase
- `brain_ds/demo.py` has a static builder for testing

#### Viewer flow (`brain_ds/ui/`)
- `cli.py` → `viewer.py:render_graph_file()` or `render_graph_data()`
- → `Graph.from_v1()` → `build_render_context(graph, workspace)` → `render_interactive_html(context)`
- → `template_renderer.py` injects CSS/JS/context JSON into `graph_viewer.html` template
- Template consumes `window.RENDER_CONTEXT` at line 894: `const RENDER_CONTEXT = __BRAIN_DS_RENDER_CONTEXT__;`
- RENDER_CONTEXT is a **static JSON object** embedded at HTML generation time — no dynamic/live data
- All JS modules (detailPanel, popover, filterPanel, search, etc.) read from this frozen object

#### SQLite graph store (`brain_ds/store/`) — ARCHIVED, do NOT modify
| Class | Purpose |
|-------|---------|
| `GraphStore(path)` | Connection lifecycle, PRAGMAs, migrations, public API |
| `GraphStore.import_json(dict)` → `graph_id` | JSON→SQLite roundtrip entry point |
| `GraphStore.load_graph(graph_id)` → `Graph` | SQLite→domain object return |
| `GraphStore.export_json(graph_id)` → `dict` | SQLite→JSON export |
| `GraphStore.list_graphs()` → `list[GraphMeta]` | Enumerate all stored graphs |
| `GraphStore.close()` | WAL checkpoint (TRUNCATE) + connection close |

**Key contract invariants** (from archived spec):
- No HTTP/CLI changes — store is an embedded library, not a service
- node.score/neighbor_count/component_id are render-derived, never persisted
- `save_graph()` / `load_graph()` roundtrip through `Graph` domain object
- Schema versioning via `store_meta` table + ordered migrations
- WAL mode + foreign keys + synchronous=NORMAL on connect

#### CWD dependencies (5 hardcoded references)
| File | Line | Usage |
|------|------|-------|
| `cli.py` | 67 | `Path.cwd() / "(stdin)"` — synthetic path for stdin mode |
| `cli.py` | 68 | Default `--root = Path.cwd().resolve()` |
| `cli.py` | 98 | Default `--root = Path.cwd().resolve()` |
| `viewer.py` | 113 | Default output `Path.cwd() / "graph-output.html"` |
| `render_context.py` | 171 | Workspace fallback root: `str(Path.cwd().resolve())` |

**No single authoritative "project root"** — the `--root` flag is optional and has no validation or convention.

#### Test coverage
| Area | Test file | Notes |
|------|-----------|-------|
| CLI | `tests/test_cli.py` (16 tests) | Covers ui/validate flags, error paths, file/stdin input |
| Viewer | `tests/test_viewer.py` (~1954 lines) | Render context, templates, interactive/simple renderers, runtime |
| Render context contract | `tests/test_render_context_contract.py` | contract_version, workspace, score/updated_at/neighbor_count |
| Runtime JS behavior | `tests/test_ui_runtime_behavior.py` (5 tests) | JS bundle behavior via Node.js harness |
| Store (10 test files) | `tests/store/` | All GraphStore operations, migrations, serialization |
| **Project scanning** | **NONE** | **No code exists. No tests exist.** |
| **HTTP server** | **NONE** | **No code exists. No tests exist.** |
| **SQLite→render integration** | **NONE** | **Does not exist yet.** |

Archive baseline: 602 passed, 4 skipped, 0 failed (from sqlite-graph-store final verify).

#### Desktop/.exe packaging constraints
- `pyproject.toml`: setuptools only — no PyInstaller/Tauri/Nuitka config
- Dependencies: `networkx` (pure Python), optional `pyvis` — no C extensions
- `sqlite3` is stdlib — no extra DLLs needed for .exe bundling
- Template assets use `importlib.resources` — works with PyInstaller package-data
- For Tauri: Python 3.11+ embedded runtime; assets in package data survive

---

### Affected Areas

- `brain_ds/ui/cli.py` — new subcommand or mode for `serve`; `graph_json` becomes optional
- `brain_ds/ui/viewer.py` — MAY expose `render_graph_from_store()` entry point
- `brain_ds/ui/render_context.py` — MAY accept `graph_id` + `GraphStore` for workspace derivation
- `brain_ds/ui/template_renderer.py` — MAY support dynamic port/resource path injection
- `brain_ds/ui/__main__.py` — no change (delegates to cli.py)
- `brain_ds/store/` — NO changes (archived contract). Consumed from outside only.
- `brain_ds/ui/templates/graph_viewer.html` — NO changes (contract frozen)
- `tests/` — new test file(s) for server mode, project scanning, store-to-render integration
- `pyproject.toml` — NO new dependencies (stdlib http.server)

### Future (Phase B/C) preparation
- `brain_ds/store/` — current GraphStore is embeddable; Tauri backend would open the same `.brain_ds/store.db`
- `brain_ds/ui/assets/` — bundles survive PyInstaller; no changes needed
- Server architecture must support future MCP WebSocket upgrade (Phase C)

---

### Approaches

#### Approach A: Static generator + file watcher (simplest, least future-proof)
`brain_ds ui` without a file argument auto-detects project, finds `graph.json`, imports to SQLite, generates HTML, opens browser. Optionally watches file for changes and regenerates.

| Pros | Cons |
|------|------|
| Zero new deps (no server) | No API surface for Phase C MCP |
| Minimal code change | Regenerate on every graph change |
| Works with current viewer unchanged | File watcher is cross-platform tricky |
| | Can't have tabbed multi-graph |

- **Effort**: Low
- **Foundation for Phase C**: Weak

#### Approach B: Dynamic HTTP server (stdlib) — RECOMMENDED
New `brain_ds ui serve` mode (or `brain_ds ui` without file arg enters serve mode). Uses Python `http.server` (stdlib). On each request: loads graph from SQLite, builds RENDER_CONTEXT dynamically, returns HTML.

| Pros | Cons |
|------|------|
| Zero new deps (http.server is stdlib) | Slightly more initial code |
| Dynamic rendering = foundation for Phase C MCP | Need to handle connection lifecycle |
| `/api/` endpoints can be added later without breaking UI | Need graceful shutdown / WAL checkpoint |
| Tauri-ready — embeddable backend | Port binding / discovery UX |
| Multi-graph tab support from R08 contract | |

- **Effort**: Medium
- **Foundation for Phase C**: Strong

#### Approach C: Third-party web framework (Flask/FastAPI)
Use a web framework for the server layer.

| Pros | Cons |
|------|------|
| Rich routing, middleware, CORS | New dependency = heavier .exe |
| Async support for SSE/WebSocket | Overkill for single-page app |
| | Conflict with zero-dep constraint |
| | Phase A only needs 1 route |

- **Effort**: Medium-High
- **Foundation for Phase C**: Medium (Flask/FastAPI would be replaced by MCP server anyway)

---

### Recommendation

**Approach B — Dynamic HTTP server using Python stdlib `http.server`.**

Rationale:
1. **Zero new dependencies** — `http.server` is stdlib, consistent with the sqlite3-only store decision
2. **Dynamic per-request rendering** — loads graph from SQLite, calls existing `build_render_context()` and `render_interactive_html()`, serves the result. All existing code is reused.
3. **Phase C MCP upgrade path** — the server loop is already running; adding a WebSocket endpoint or `/api/` routes is additive
4. **Tauri-ready** — the server process can be spawned and managed by a Tauri Rust backend; port can be piped to the webview
5. **Multi-graph tab support** — R08 TabModel schema already exists; list graphs from SQLite via `list_graphs()`, let tabs switch between graph_ids
6. **WAL checkpoint on graceful shutdown** — `SIGINT`/`SIGTERM` handler calls `GraphStore.close()`

**CLI design**: `brain_ds ui` without `graph_json` argument enters project-scoped serve mode.
- `brain_ds ui serve` subcommand (explicit) — also supported for discoverability
- `--port` (default 8765), `--project-root` (default CWD), `--open` (open browser)
- `brain_ds ui <graph_json>` stays unchanged — **backward compatible**

**Project storage convention**:
```
{project-root}/
  .brain_ds/           ← hidden workspace directory
    store.db           ← SQLite graph store (one file, multi-graph)
```

**Server startup flow**:
1. Resolve project root (CLI arg or CWD)
2. Ensure `{project-root}/.brain_ds/` exists
3. Create/open `{project-root}/.brain_ds/store.db` via `GraphStore`
4. Scan project root + `.brain_ds/` for known graph JSON files
5. Import unknown graphs into SQLite stores (dedup by path)
6. Start `http.server.HTTPServer` on `0.0.0.0:{port}`
7. `GET /` → load active graph from SQLite → `build_render_context()` → `render_interactive_html()` → return HTML
8. `GET /api/graphs` → `store.list_graphs()` → JSON (Phase A readiness, not full MCP)
9. Handle SIGINT/SIGTERM → `store.close()` → exit

---

### Risks

1. **CWD assumptions (MEDIUM)**: 5 hardcoded `Path.cwd()` references in cli.py, viewer.py, render_context.py. The server MUST resolve project root ONCE at startup and pass `WorkspaceContext` explicitly — not rely on CWD. Every current CWD call site needs audit and replacement with the resolved project root.

2. **Multi-graph state (LOW)**: R08 TabModel schema exists but the UI has never been tested with multiple tabs pointing to different graph_ids. The server needs to choose which graph is "active" on first load — probably the most recent one from `list_graphs()`.

3. **Store DB lifetime (MEDIUM)**: `GraphStore` is designed for short-lived connections (import → load → close). In server mode, the connection is long-lived. WAL mode handles concurrent readers, but the server must ensure:
   - `GraphStore.close()` is called on graceful shutdown
   - WAL checkpoint runs before exit (already in `close()`)
   - Read-only access for serving; write access only during import

4. **Port conflicts (LOW)**: Default port 8765 may be in use. Server should retry port+1 or log a clear error.

5. **No project scanning code exists (HIGH)**: There is no existing concept of "scan the project for graph data." The MVP interpretation: scan for `*.json` files with graph JSON schema at the project root and `.brain_ds/`. Future Phase C will add more sophisticated scanning.

6. **Windows path handling (LOW)**: `http.server` handles POSIX paths internally. WorkspaceContext in R02 contract requires POSIX-style `displayPath`. Must test on Windows to ensure `WorkspaceContext.displayPath` stays forward-slash.

7. **Template resource resolution (LOW)**: `render_interactive_html` uses `importlib.resources` to find templates. This works at dev time and in installed packages, but PyInstaller may need explicit data inclusion.

8. **Phase C MCP WebSocket architecture unknown (MEDIUM)**: The server built in Phase A will later need a WebSocket upgrade for MCP. Using `http.server` + threading makes WS harder. For Phase A it's fine — the WS upgrade is a Phase C concern and `http.server` can be replaced or extended at that point.

9. **Future-check signposts from sqlite-graph-store archive**:
   - `:memory:` WAL behavior: server uses file-backed DB, so WAL is real, not simulated
   - Coverage tooling unavailable for server tests
   - `wal_checkpoint(TRUNCATE)` assertions are brittle cross-platform
   - Keep design/spec/apply/verify references synchronized after remediation

---

### Ready for Proposal

Yes. Recommended scope for proposal:

- **New CLI mode**: `brain_ds ui` without file argument (or `brain_ds ui serve`) enters project-scoped serve mode
- **New file**: `brain_ds/ui/server.py` — HTTP request handler + server lifecycle
- **Modified file**: `brain_ds/ui/cli.py` — add serve subcommand / make graph_json optional with serve fallback
- **Modified file**: `brain_ds/ui/__init__.py` — export new serve function if needed
- **Storage convention**: `{project-root}/.brain_ds/store.db`
- **No new dependencies** — stdlib `http.server` + existing `render_interactive_html`
- **No changes to**: `brain_ds/store/` (archived, consumed as-is), `brain_ds/ui/templates/` (contract frozen), `brain_ds/ontology/` (unchanged)
- **Tests**: server startup, project-root resolution, store integration, graceful shutdown, Windows path handling
- **Non-goals**: file watching, auto-reload, MCP/WebSocket, /api/ beyond graph listing, multi-user, CI/CD auto-deploy
