# Design: project-scoped-runtime

## Technical Approach

Convert the `brain_ds ui` command from a one-shot static HTML generator into a long-lived, project-scoped HTTP server. We will use the standard library `http.server` to serve the UI dynamically from a `.brain_ds/store.db` SQLite store (using the existing `GraphStore`). The CLI will resolve the workspace root once at startup, encapsulate it in an updated `WorkspaceContext`, and pass it down to eliminate scattered `Path.cwd()` assumptions. A minimal depth-1 JSON scanner will populate the store at startup.

## Architecture Decisions

### Decision: Loopback-only server binding
**Choice**: Bind `http.server` exclusively to `127.0.0.1`.
**Alternatives considered**: Binding to `0.0.0.0` or providing a host flag.
**Rationale**: Aligns with the desktop-local threat model. Security by default prevents external access without complex authentication.

### Decision: Store connection lifecycle
**Choice**: Open a single `GraphStore` connection at server startup and close it gracefully on `SIGINT`/`SIGTERM`.
**Alternatives considered**: Open/close per request.
**Rationale**: SQLite with WAL allows concurrent readers. A long-lived connection reduces overhead and allows the server to hold the lock predictably. The shutdown hook ensures WAL checkpoints execute cleanly.

### Decision: WorkspaceContext as single source of truth
**Choice**: Refactor `WorkspaceContext` to contain `project_root`, `display_path`, and `store_path` (as `pathlib.Path`), resolved exactly once in `cli.py`.
**Alternatives considered**: Passing independent string arguments.
**Rationale**: Eliminates all 5 hardcoded `Path.cwd()` sites, making the codebase robust for desktop/GUI environments where the current working directory may differ from the project root.

### Decision: Project-scan MVP
**Choice**: Depth-1 scan of `project_root` and `project_root/.brain_ds/` for `.json` files at server startup. Import valid graphs if not already present.
**Alternatives considered**: Recursive scan or no scan.
**Rationale**: Recursive is too slow/complex for Phase A. A depth-1 scan is just enough to migrate existing static graphs into the DB for the new UI to consume.

### Decision: Active graph selection
**Choice**: Serve the most recently updated graph (by `updated_at`) on `GET /`.
**Alternatives considered**: Alphabetical by label, or returning a picker UI.
**Rationale**: Multi-graph swap UI is deferred to Phase C. Sorting by recent activity provides the best zero-config experience.

## Data Flow

```text
[ CLI: brain_ds ui serve ]
         │
         ▼ (resolve paths)
[ WorkspaceContext ] ──────────┐
         │                     │
         ▼ (scan JSON)         │
[ GraphStore (SQLite) ]        │
         │                     │
         ▼ (start)             ▼
[ Server (http.server) ] ──▶ [ GET / ]
         │                     │
         ▼                     ▼
[ Signal Handler ]         [ render_interactive_html ]
   (checkpoint WAL)            (returns HTML)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `brain_ds/ui/server.py` | Create | Implements `http.server` handler, startup scanner, and shutdown signals. |
| `brain_ds/ui/render_context.py` | Modify | Update `WorkspaceContext` dataclass. Remove `Path.cwd()` at line 171. |
| `brain_ds/ui/cli.py` | Modify | Support `brain_ds ui [serve]` and `brain_ds ui <file>`. Thread `WorkspaceContext`. Remove `Path.cwd()` at lines 67, 68, 98. |
| `brain_ds/ui/viewer.py` | Modify | Accept updated `WorkspaceContext`. Remove `Path.cwd()` at line 113. |
| `brain_ds/store/graph_store.py` | Modify | Allow runtime server access from request threads via optional `allow_cross_thread=True` connection mode. |
| `tests/test_server.py` | Create | TDD coverage for `/`, `/api/graphs`, shutdown, and port conflict. |
| `tests/test_cli_serve.py` | Create | TDD coverage for `serve` mode parsing and `WorkspaceContext` creation. |
| `tests/test_workspace.py` | Create | TDD coverage for path resolution, Windows display paths, and no-cwd enforcement. |
| `tests/test_scanner.py` | Create | TDD coverage for depth-1 scan behavior, dedupe by source path, and malformed JSON skip/log behavior. |
| `tests/test_regression.py` | Create | Runtime regression coverage for stdlib-only import surface and threaded active-graph contract behavior. |

## Interfaces / Contracts

```python
# brain_ds/ui/render_context.py
@dataclass(frozen=True)
class WorkspaceContext:
    project_root: Path
    display_path: str
    store_path: Path

# brain_ds/ui/server.py
def run_server(workspace: WorkspaceContext, port: int, open_browser: bool) -> int:
    # 1. Initialize GraphStore at workspace.store_path
    # 2. Run depth-1 scan and import
    # 3. Start http.server on 127.0.0.1:port
    # 4. Handle SIGINT/SIGTERM -> close store, return 0
    pass
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `WorkspaceContext` | Assert `Path` types, correct relative `display_path` generation, Windows path slash conversion. |
| Unit | CLI parser | Assert `ui` with no args or `serve` activates server mode; `ui <file>` retains legacy path. |
| Integration | Server startup | Assert `run_server` raises on port conflict; assert `GraphStore` creates DB file. |
| E2E | HTTP routes | Spin up server thread, request `GET /` and `GET /api/graphs`, assert 200 OK and expected JSON/HTML payload. |
| E2E | CWD regression | Run CLI/serve via mock, assert `pathlib.Path.cwd` is never called within `viewer.py` or `render_context.py`. |

## Migration / Rollout

No data migration required. The `GraphStore` schema from the previous phase is used directly. Legacy JSON files in the project root will be automatically imported into the SQLite store on first `serve` launch.

## Open Questions

- [ ] **Scan import errors**: Should the depth-1 scan fail fast or log-and-skip on malformed JSON? (Recommendation: log-and-skip).
- [ ] **`/api/graphs` shape**: Should it return a minimal `{id, label}` array or the full TabModel used in older prototypes? (Recommendation: minimal array for now).
