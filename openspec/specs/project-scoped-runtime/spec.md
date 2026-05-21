# Spec: project-scoped-runtime

## Purpose

Defines the behavior for the `brain_ds ui` project-scoped runtime, including local workspace resolution, SQLite `GraphStore` integration, dynamic template rendering, and graceful shutdown, while preserving the legacy static HTML generation path.

## ADDED Requirements

### Requirement: CLI Surface and Serve Mode

The system MUST support `brain_ds ui` (no args) and `brain_ds ui serve` to start the project-scoped HTTP server on the loopback interface using the standard library `http.server`. It MUST preserve `brain_ds ui <graph_json>` for legacy static generation.

#### Scenario: No arguments starts serve mode

- GIVEN a terminal at a project root
- WHEN `brain_ds ui` is executed
- THEN it MUST start the HTTP server on the loopback interface (127.0.0.1)
- AND default to port 8765

#### Scenario: Legacy static generation is preserved

- GIVEN a valid `graph.json`
- WHEN `brain_ds ui graph.json` is executed
- THEN it MUST output the static HTML to stdout (or a file if redirected)
- AND MUST NOT start the HTTP server

#### Scenario: Explicit serve subcommand

- GIVEN a terminal
- WHEN `brain_ds ui serve --port 9000` is executed
- THEN it MUST start the HTTP server on port 9000

---

### Requirement: Workspace Context and Path Resolution

The system MUST resolve the workspace root once at startup into a `WorkspaceContext`. It MUST create and use `.brain_ds/store.db` at the resolved root without modifying the archived `GraphStore` contract. The runtime MUST NOT call `Path.cwd()` during request handling.

#### Scenario: First launch creates store

- GIVEN a project without a `.brain_ds/` directory
- WHEN the server starts
- THEN it MUST create the `.brain_ds` hidden directory
- AND initialize the SQLite `store.db` within it

#### Scenario: Windows path normalization

- GIVEN the server is running on Windows
- WHEN the `display_path` is resolved in `WorkspaceContext`
- THEN it MUST use forward slashes (e.g., `C:/path/to/project`)

#### Scenario: No CWD dependency during render

- GIVEN an active HTTP request
- WHEN `build_render_context` is executed
- THEN it MUST use the `WorkspaceContext` path
- AND MUST NOT call `Path.cwd()`

---

### Requirement: Initial Graph Scanning

The system MUST perform a depth-1 scan of the project root and `.brain_ds/` directory on startup to discover and import valid graph JSON files into the `GraphStore`.

#### Scenario: Import unindexed graph JSON

- GIVEN a valid `v1` graph JSON file exists in the project root
- AND it is not yet in the `GraphStore`
- WHEN the server starts
- THEN it MUST import the JSON into the `GraphStore`

#### Scenario: Skip invalid or nested files

- GIVEN a JSON file in a nested directory (`src/data.json`)
- WHEN the server starts
- THEN it MUST NOT scan or import the nested file

---

### Requirement: HTTP Server and Dynamic Rendering

The server MUST handle `GET /` by rendering the UI template dynamically using data from the most recently updated graph in the `GraphStore` via the existing `RENDER_CONTEXT` pipeline. It MUST provide a `GET /api/graphs` endpoint returning a list of available graphs. It MUST NOT introduce new third-party dependencies.

#### Scenario: Dynamic render of active graph

- GIVEN multiple graphs in the `GraphStore`
- WHEN a client requests `GET /`
- THEN the system MUST identify the most recently updated graph
- AND return a 200 OK with the rendered HTML containing that graph's data

#### Scenario: Empty store renders gracefully

- GIVEN an empty `GraphStore`
- WHEN a client requests `GET /`
- THEN it MUST render the UI with an empty or default RENDER_CONTEXT

#### Scenario: API endpoint for graph list

- GIVEN the server is running
- WHEN a client requests `GET /api/graphs`
- THEN it MUST return a JSON array containing graph IDs and labels

---

### Requirement: Server Lifecycle and Graceful Shutdown

The server MUST handle SIGINT and SIGTERM signals by shutting down the HTTP listener and gracefully closing the `GraphStore` connection, ensuring SQLite WAL checkpoints are executed.

#### Scenario: Graceful shutdown on SIGINT

- GIVEN the server is running
- WHEN a SIGINT (Ctrl+C) is received
- THEN it MUST close the `GraphStore` connection
- AND exit cleanly with status code 0
- AND ensure no orphan WAL/SHM files remain in the happy path

#### Scenario: Port conflict fails fast

- GIVEN another process is already bound to port 8765
- WHEN the server attempts to start on port 8765
- THEN it MUST emit a clear error message
- AND exit with status code 1 without retrying

---

## Architecture Decisions

### Decision: Loopback-only server binding
**Choice**: Bind `http.server` exclusively to `127.0.0.1`.
**Rationale**: Aligns with the desktop-local threat model. Security by default prevents external access without complex authentication.

### Decision: Store connection lifecycle
**Choice**: Open a single `GraphStore` connection at server startup and close it gracefully on `SIGINT`/`SIGTERM`.
**Rationale**: SQLite with WAL allows concurrent readers. A long-lived connection reduces overhead and allows the server to hold the lock predictably. The shutdown hook ensures WAL checkpoints execute cleanly.

### Decision: WorkspaceContext as single source of truth
**Choice**: Refactor `WorkspaceContext` to contain `project_root`, `display_path`, and `store_path` (as `pathlib.Path`), resolved exactly once in `cli.py`.
**Rationale**: Eliminates all 5 hardcoded `Path.cwd()` sites, making the codebase robust for desktop/GUI environments where the current working directory may differ from the project root.

### Decision: Project-scan MVP
**Choice**: Depth-1 scan of `project_root` and `project_root/.brain_ds/` for `.json` files at server startup. Import valid graphs if not already present.
**Rationale**: Minimal complexity to get graphs into the DB for Phase A before manual editing (Phase C) is built.

### Decision: Active graph selection
**Choice**: Serve the most recently updated graph (by `updated_at`) on `GET /`.
**Rationale**: Multi-graph swap UI is deferred to Phase C. Sorting by recent activity provides the best zero-config experience.

## Preserved Constraints

- **RENDER_CONTEXT contract**: Unchanged at version 1.0.0. Static-generation path (`brain_ds ui <graph_json>`) produces identical HTML.
- **GraphStore contract**: Consumed unmodified from archived `sqlite-graph-store`. No schema changes, no new public methods.
- **Zero new third-party dependencies**: Use only Python standard library (`http.server`, `pathlib`, `signal`, `json`).
