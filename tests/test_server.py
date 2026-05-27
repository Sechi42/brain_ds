import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from brain_ds.ontology import Graph


def _sample_graph_payload(org: str) -> dict:
    return {
        "org": org,
        "generated_at": "2026-03-01T08:00:00Z",
        "nodes": [{"id": "n1", "label": f"{org} Node", "type": "Department"}],
        "edges": [],
        "evidence": [],
    }


class TestServerRuntime(unittest.TestCase):
    def test_run_server_creates_workspace_store_when_missing(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            self.assertFalse(store_path.exists())

            fake_server = Mock()
            fake_server.config.bind_socket.return_value = None
            with patch("brain_ds.ui.server.uvicorn.Server", return_value=fake_server), patch("brain_ds.ui.server.signal.signal"):
                server.run_server(project_root=root, port=8765)

            self.assertTrue(store_path.exists())
            fake_server.run.assert_called_once()

    def test_run_server_port_conflict_reports_clear_error_and_exits_1(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stderr(stderr):
                    fake_server = Mock()
                    fake_server.config.bind_socket.side_effect = OSError("Address in use")
                    with patch("brain_ds.ui.server.uvicorn.Server", return_value=fake_server):
                        server.run_server(project_root=root, port=8765)

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Error: port 8765 is already in use", stderr.getvalue())

    def test_get_root_returns_rendered_html_from_active_graph(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = [
                SimpleNamespace(id="old-id", org="Older Org", imported_from=str(root / "old.json")),
                SimpleNamespace(id="new-id", org="Latest Org", imported_from=str(root / "new.json")),
            ]
            fake_store.load_graph.return_value = Graph.from_v1(_sample_graph_payload("Latest Org"))

            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("Latest Org", response.text)

    def test_get_root_with_empty_store_returns_200(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = []

            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("RENDER_CONTEXT", response.text)

    def test_get_api_graphs_returns_id_and_label_json(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = [
                SimpleNamespace(id="graph-1", org="Label Org", imported_from=str(root / "graph.json"))
            ]
            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/api/graphs")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [{"id": "graph-1", "label": "Label Org"}])

    def test_sigint_handler_closes_store_and_exits_0(self):
        from brain_ds.ui import server

        runtime = server.ServerRuntime(project_root=Path("."), store=Mock())
        fake_httpd = SimpleNamespace(shutdown=Mock())

        with self.assertRaises(SystemExit) as ctx:
            runtime._handle_signal(2, None, fake_httpd)

        self.assertEqual(ctx.exception.code, 0)
        runtime.store.close.assert_called_once()
        fake_httpd.shutdown.assert_called_once()

    def test_sigint_handler_closes_file_backed_store_and_releases_wal_shm_handles(self):
        from brain_ds.store.graph_store import GraphStore
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store = GraphStore(str(store_path))
            store.import_json(_sample_graph_payload("Wal Org"), workspace_root=str(root))

            runtime = server.ServerRuntime(project_root=root, store=store)
            fake_httpd = SimpleNamespace(shutdown=Mock())

            with self.assertRaises(SystemExit) as ctx:
                runtime._handle_signal(2, None, fake_httpd)

            self.assertEqual(ctx.exception.code, 0)
            self.assertTrue(store._closed)
            fake_httpd.shutdown.assert_called_once()

            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{store_path}{suffix}")
                if sidecar.exists():
                    renamed = sidecar.with_name(sidecar.name + ".moved")
                    sidecar.rename(renamed)
                    renamed.unlink()
                self.assertFalse(sidecar.exists(), f"Expected {sidecar.name} to be absent after shutdown")
