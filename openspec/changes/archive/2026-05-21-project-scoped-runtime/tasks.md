# Tasks: project-scoped-runtime

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~950 (server.py 280, cli.py 80, WorkspaceContext 60, CWD swaps 40, tests 520) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Base | ~Lines |
|------|------|-----|------|--------|
| 1 | WorkspaceContext refactor + CWD elimination (no behavior change) | PR 1 | main | 210 |
| 2 | server.py core: routes, store lifecycle, shutdown | PR 2 | PR 1 | 430 |
| 3 | CLI serve wiring + depth-1 JSON scanner | PR 3 | PR 2 | 150 |
| 4 | Regression checks: legacy compat, CWD audit, integration | PR 4 | PR 3 | 160 |

## Phase 1: Foundation — WorkspaceContext (PR 1)

- [x] 1.1 RED: tests/test_workspace.py — assert WorkspaceContext fields: project_root(Path), display_path(str), store_path(Path)
- [x] 1.2 GREEN: render_context.py — extend dataclass with new fields; keep old ones as deprecated aliases
- [x] 1.3 RED: tests/test_workspace.py — assert Windows display_path uses forward slashes; store_path = {root}/.brain_ds/store.db
- [x] 1.4 GREEN: render_context.py — _compute_workspace_meta uses new fields; remove Path.cwd() fallback at line 171
- [x] 1.5 RED: tests/test_viewer.py — mock-assert render_graph_file never calls Path.cwd()
- [x] 1.6 GREEN: viewer.py line 113 — use workspace store_path parent instead of Path.cwd() for default output
- [x] 1.7 GREEN: cli.py lines 67,68,98 — resolve root once in main(), thread via WorkspaceContext; remove Path.cwd()
- [x] 1.8 Verify: full suite green; grep proves zero Path.cwd() in serve code path

## Phase 2: Server Core (PR 2)

- [x] 2.1 RED: tests/test_server.py — assert run_server raises on port conflict, exits 1
- [x] 2.2 GREEN: brain_ds/ui/server.py — BaseHTTPRequestHandler subclass, run_server() lifecycle, bind 127.0.0.1
- [x] 2.3 RED: tests/test_server.py — assert GET / returns 200 with rendered HTML from active graph in GraphStore
- [x] 2.4 GREEN: server.py — GET /: list_graphs()→most recent, load_graph(), build_render_context()+render_interactive_html()
- [x] 2.5 RED: tests/test_server.py — assert empty store GET / returns 200 with default context (no crash)
- [x] 2.6 GREEN: server.py — fallback to empty RENDER_CONTEXT when store has no graphs
- [x] 2.7 RED: tests/test_server.py — assert GET /api/graphs returns [{id, label}] JSON array
- [x] 2.8 GREEN: server.py — /api/graphs: list_graphs()→json.dumps
- [x] 2.9 RED: tests/test_server.py — assert SIGINT triggers store.close() with WAL checkpoint, exit 0
- [x] 2.10 GREEN: server.py — signal.signal(SIGINT/SIGTERM)→store.close(); no orphan WAL/SHM

## Phase 3: CLI Wiring & Scanner (PR 3)

- [x] 3.1 RED: tests/test_cli_serve.py — assert brain_ds ui (no args) invokes run_server
- [x] 3.2 GREEN: cli.py — ui subcommand: no arg → serve mode; --port flag; --project-root flag; resolve root at main()
- [x] 3.3 RED: tests/test_cli_serve.py — assert brain_ds ui serve --port 9000 passes to run_server
- [x] 3.4 RED: tests/test_server.py — assert startup creates .brain_ds/ + store.db when missing
- [x] 3.5 GREEN: server.py — ensure .brain_ds dir + store.db initialized before server.listen
- [x] 3.6 RED: tests/test_scanner.py — assert depth-1 scan imports v1 JSON, skips nested dirs, log-and-skip on invalid
- [x] 3.7 GREEN: server.py — _scan_project_root(): glob root/*.json + .brain_ds/*.json; import_json() if not in store

## Phase 4: Regression & Integration (PR 4)

- [x] 4.1 RED: tests/test_cli_serve.py — assert brain_ds ui graph.json static path unchanged (golden fixture parity)
- [x] 4.2 GREEN: cli.py — preserve legacy _run_ui path; positional graph_json arg triggers static mode
- [x] 4.3 RED: tests/test_regression.py — assert no new third-party imports in server.py or cli.py
- [x] 4.4 RED: tests/test_regression.py — end-to-end: temp project, 2-graph fixture, serve GET /, verify RENDER_CONTEXT contract v1.0.0
- [x] 4.5 GREEN: integration — real HTTP request/response cycle with thread-based server, assert 200 + contract integrity
- [x] 4.6 Verify: uv run python -m unittest discover -s tests — all green, zero regressions, zero new deps
