from __future__ import annotations

import json
import signal
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: F401  (re-exported for runtime/tests)
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from brain_ds.api.server import create_app
from brain_ds.ontology import Graph
from brain_ds.store.errors import GraphNotFoundError
from brain_ds.store.graph_store import GraphStore
from brain_ds.workspaces import delete_workspace_store, register_workspace, unregister_workspace

from .render_context import WorkspaceContext, build_render_context
from .template_renderer import render_interactive_html, render_vault_picker_html


def _empty_graph() -> Graph:
    return Graph.from_v1({"nodes": [], "edges": []})


def _workspace_confirm_matches(workspace_root: Path, typed_confirm: str) -> bool:
    candidate = typed_confirm.strip()
    if not candidate:
        return False
    resolved = workspace_root.resolve()
    return candidate in {resolved.name, str(resolved)} or Path(candidate).resolve() == resolved


class ServerRuntime:
    def __init__(self, *, project_root: Path, store: GraphStore):
        self.project_root = project_root.resolve()
        self.store = store

    def _active_graph_payload(self) -> tuple[Graph, WorkspaceContext, str]:
        graphs = self.store.list_graphs()
        if not graphs:
            workspace = WorkspaceContext.from_root_and_graph(self.project_root, self.project_root / "graph.json")
            return _empty_graph(), workspace, ""

        # GraphStore.list_graphs() owns the active-graph ordering contract
        # (most recently updated first). Re-sorting here creates flaky UUID
        # tie-breaks when two graphs are saved inside the same timestamp tick.
        active = graphs[0]
        graph = self.store.load_graph(active.id)
        imported_from = Path(active.imported_from).resolve() if active.imported_from else self.project_root / "graph.json"
        workspace = WorkspaceContext.from_root_and_graph(self.project_root, imported_from)
        return graph, workspace, active.id

    def _graphs_payload(self) -> list[dict[str, str]]:
        return [{"id": item.id, "label": item.org or item.id} for item in self.store.list_graphs()]

    def _graph_payload_for(self, graph_id: str) -> tuple[Graph, WorkspaceContext, str]:
        """Load a specific graph by id; falls back to auto-pick on unknown id (R7)."""
        try:
            graph = self.store.load_graph(graph_id)
            graphs = self.store.list_graphs()
            meta = next((g for g in graphs if g.id == graph_id), None)
            imported_from = (
                Path(meta.imported_from).resolve()
                if meta and meta.imported_from
                else self.project_root / "graph.json"
            )
            workspace = WorkspaceContext.from_root_and_graph(self.project_root, imported_from)
            return graph, workspace, graph_id
        except GraphNotFoundError:
            return self._active_graph_payload()

    def _render_root_html(self, graph_id: str | None = None) -> str:
        workspace = WorkspaceContext.from_root_and_graph(self.project_root, self.project_root / "graph.json")
        resolved_graph_id = ""
        try:
            if graph_id:
                graph, workspace, resolved_graph_id = self._graph_payload_for(graph_id)
            else:
                graph, workspace, resolved_graph_id = self._active_graph_payload()
        except Exception:
            graph = _empty_graph()
        context = build_render_context(graph, workspace=workspace, graph_id=resolved_graph_id)
        return render_interactive_html(context)

    def _handle_signal(self, signum: int, frame: Any, server: Any = None) -> None:
        self.store.close()
        if server is not None:
            if hasattr(server, "shutdown"):
                server.shutdown()
            if hasattr(server, "should_exit"):
                server.should_exit = True
        raise SystemExit(0)

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        runtime = self

        class RuntimeHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/":
                    html = runtime._render_root_html().encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                    return

                if self.path == "/api/graphs":
                    payload = json.dumps(runtime._graphs_payload()).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                self.send_error(HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return RuntimeHandler


def build_ui_app(*, project_root: Path, store: GraphStore) -> FastAPI:
    runtime = ServerRuntime(project_root=project_root, store=store)
    app = create_app(project_root=project_root, store=store)

    @app.get("/")
    def root_page(graph_id: str | None = None) -> HTMLResponse:
        return HTMLResponse(runtime._render_root_html(graph_id=graph_id))

    @app.get("/api/graphs")
    def list_graphs() -> JSONResponse:
        return JSONResponse(runtime._graphs_payload())

    @app.get("/vault-picker")
    def vault_picker() -> HTMLResponse:
        """R8/R9: list all orgs as focusable rows + always-present create-org form."""
        graphs = runtime._graphs_payload()
        return HTMLResponse(render_vault_picker_html(graphs))

    @app.delete("/api/graphs/{graph_id}")
    def delete_graph_route(graph_id: str, hard: bool = False, body: dict = Body(default={})) -> JSONResponse:
        """Soft-delete (default) or hard-delete a graph by UUID.

        - ``hard=false`` (default): marks the graph hidden via the ``hidden``
          column. Data survives; the graph disappears from list/picker. Reversible.
        - ``hard=true``: permanently deletes the graph row and all attached data
          (nodes/edges/evidence via ON DELETE CASCADE). Requires
          ``{"typed_confirm": "<graph label or id>"}`` in the request body.
        """
        typed_body = body if isinstance(body, dict) else {}

        if hard:
            # Require a confirm token matching the graph label or id
            typed_confirm = str(typed_body.get("typed_confirm", "")).strip()
            if not typed_confirm:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "typed_confirm is required for hard delete"},
                )
            # Fetch graph meta to validate confirm token
            try:
                graphs = runtime.store.meta_repo.list_graphs(include_hidden=True)
                meta = next((g for g in graphs if g.id == graph_id), None)
            except Exception:
                meta = None
            if meta is None:
                return JSONResponse(status_code=404, content={"detail": f"Graph '{graph_id}' not found"})
            if typed_confirm not in {meta.id, meta.org}:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "typed_confirm must match the graph label or id"},
                )
            try:
                runtime.store.delete_graph(graph_id)
            except GraphNotFoundError:
                return JSONResponse(status_code=404, content={"detail": f"Graph '{graph_id}' not found"})
            return JSONResponse(content={"id": graph_id, "deleted": True})

        # Soft delete: hide
        try:
            runtime.store.hide_graph(graph_id)
        except GraphNotFoundError:
            return JSONResponse(status_code=404, content={"detail": f"Graph '{graph_id}' not found"})
        return JSONResponse(content={"id": graph_id, "hidden": True})

    @app.delete("/api/workspaces/{path:path}")
    def delete_workspace(path: str, delete_store: bool = False, body: dict = Body(default={})) -> JSONResponse:
        workspace_root = Path(path)
        typed_confirm = str(body.get("typed_confirm", "")).strip() if isinstance(body, dict) else ""

        if delete_store:
            if not typed_confirm:
                return JSONResponse(status_code=422, content={"detail": "typed_confirm is required when delete_store=true"})
            if not _workspace_confirm_matches(workspace_root, typed_confirm):
                return JSONResponse(status_code=422, content={"detail": "typed_confirm must match the workspace name or path"})
            try:
                if workspace_root.resolve() == runtime.project_root.resolve():
                    runtime.store.close()
                delete_workspace_store(workspace_root, confirm_token=typed_confirm)
            except ValueError as exc:
                return JSONResponse(status_code=422, content={"detail": str(exc)})

        unregister_workspace(workspace_root)
        return JSONResponse(content={"path": str(workspace_root), "deleted_store": bool(delete_store)})

    @app.post("/api/setup-mcp")
    def setup_mcp(body: dict = Body(default={})) -> JSONResponse:
        """Configure brain_ds MCP clients for this project from inside the desktop UI."""
        from .setup import apply_setup

        agent = str(body.get("agent", "both")) if isinstance(body, dict) else "both"
        if agent not in {"claude", "opencode", "both"}:
            return JSONResponse(status_code=400, content={"detail": "agent must be claude, opencode or both"})
        try:
            result = apply_setup(runtime.project_root, agent=agent)
        except OSError as exc:
            return JSONResponse(status_code=500, content={"detail": str(exc)})
        return JSONResponse(content=result)

    @app.post("/api/graphs", status_code=201)
    def create_graph(body: dict = Body(...)) -> JSONResponse:
        raw_label = body.get("label", "") if isinstance(body, dict) else ""
        label = str(raw_label).strip()
        if not label:
            return JSONResponse(
                status_code=400,
                content={"detail": "label must not be empty or whitespace"},
            )
        graph = Graph.from_v1({"nodes": [], "edges": [], "org": label})
        new_id = runtime.store.save_graph(
            graph, workspace_root=str(runtime.project_root)
        )
        return JSONResponse(
            status_code=201,
            content={"id": new_id, "label": label},
        )

    return app


def _resolve_store_path(project_root: Path) -> Path:
    store_dir = project_root / ".brain_ds"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir / "store.db"


def _scan_project_root(project_root: Path, store: GraphStore) -> list[str]:
    root = project_root.resolve()
    imported = []
    known_sources = {
        str(Path(item.imported_from).resolve())
        for item in store.list_graphs()
        if item.imported_from
    }

    candidates = list(root.glob("*.json"))
    workspace_dir = root / ".brain_ds"
    if workspace_dir.exists():
        candidates.extend(workspace_dir.glob("*.json"))

    for candidate in candidates:
        source_path = str(candidate.resolve())
        if source_path in known_sources:
            continue

        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and "imported_from" not in payload:
                payload["imported_from"] = source_path
            graph_id = store.import_json(payload, workspace_root=str(root))
            imported.append(graph_id)
            known_sources.add(source_path)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            print(f"Skipping invalid graph JSON: {candidate} ({exc})", file=sys.stderr)

    return imported


def scan_project_root(*, project_root: Path) -> list[str]:
    root = project_root.resolve()
    store_path = _resolve_store_path(root)
    store = GraphStore(str(store_path))
    try:
        return _scan_project_root(root, store)
    finally:
        store.close()


def run_server(*, project_root: Path, port: int = 8765) -> None:
    root = project_root.resolve()
    store_path = _resolve_store_path(root)
    store = GraphStore(str(store_path), allow_cross_thread=True)
    # Desktop vault-picker flow: opening a folder makes it globally
    # discoverable (Obsidian-style) for MCP clients in other sessions.
    try:
        register_workspace(root)
    except OSError:
        pass
    _scan_project_root(root, store)
    runtime = ServerRuntime(project_root=root, store=store)
    app = build_ui_app(project_root=root, store=store)
    try:
        config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        try:
            server.config.bind_socket()
        except OSError as exc:
            print(f"Error: port {port} is already in use", file=sys.stderr)
            raise SystemExit(1) from exc

        signal.signal(signal.SIGINT, lambda s, f: runtime._handle_signal(s, f, server))
        signal.signal(signal.SIGTERM, lambda s, f: runtime._handle_signal(s, f, server))
        server.run()
    finally:
        store.close()
