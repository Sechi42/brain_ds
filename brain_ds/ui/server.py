from __future__ import annotations

import json
import signal
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from brain_ds.ontology import Graph
from brain_ds.store.graph_store import GraphStore

from .render_context import WorkspaceContext, build_render_context
from .template_renderer import render_interactive_html


def _empty_graph() -> Graph:
    return Graph.from_v1({"nodes": [], "edges": []})


class ServerRuntime:
    def __init__(self, *, project_root: Path, store: GraphStore):
        self.project_root = project_root.resolve()
        self.store = store

    def _active_graph_payload(self) -> tuple[Graph, WorkspaceContext]:
        graphs = self.store.list_graphs()
        if not graphs:
            workspace = WorkspaceContext.from_root_and_graph(self.project_root, self.project_root / "graph.json")
            return _empty_graph(), workspace

        active = max(
            graphs,
            key=lambda item: (
                str(getattr(item, "updated_at", "") or ""),
                str(getattr(item, "generated_at", "") or ""),
                str(getattr(item, "id", "") or ""),
            ),
        )
        graph = self.store.load_graph(active.id)
        imported_from = Path(active.imported_from).resolve() if active.imported_from else self.project_root / "graph.json"
        workspace = WorkspaceContext.from_root_and_graph(self.project_root, imported_from)
        return graph, workspace

    def _graphs_payload(self) -> list[dict[str, str]]:
        return [{"id": item.id, "label": item.org or item.id} for item in self.store.list_graphs()]

    def _render_root_html(self) -> str:
        graph, workspace = self._active_graph_payload()
        context = build_render_context(graph, workspace=workspace)
        return render_interactive_html(context)

    def _handle_signal(self, signum: int, frame: Any, httpd: ThreadingHTTPServer) -> None:
        self.store.close()
        httpd.shutdown()
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
        if getattr(item, "imported_from", None)
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
    _scan_project_root(root, store)
    runtime = ServerRuntime(project_root=root, store=store)
    try:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), runtime.handler_class())
        except OSError as exc:
            print(f"Error: port {port} is already in use", file=sys.stderr)
            raise SystemExit(1) from exc

        signal.signal(signal.SIGINT, lambda s, f: runtime._handle_signal(s, f, httpd))
        signal.signal(signal.SIGTERM, lambda s, f: runtime._handle_signal(s, f, httpd))
        httpd.serve_forever()
    finally:
        store.close()
