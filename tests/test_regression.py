import ast
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

from brain_ds.store.graph_store import GraphStore
from brain_ds.ui import server


def _valid_graph(org: str, *, generated_at: str = "2026-03-01T08:00:00Z") -> dict:
    return {
        "org": org,
        "generated_at": generated_at,
        "nodes": [{"id": "n1", "label": f"{org} Node", "type": "Department"}],
        "edges": [],
        "evidence": [],
    }


class TestRuntimeRegression(unittest.TestCase):
    def test_ui_runtime_modules_use_only_stdlib_and_project_imports(self):
        project_root = Path(__file__).resolve().parents[1]
        allowed_roots = {
            "__future__",
            "argparse",
            "json",
            "pathlib",
            "sys",
            "typing",
            "signal",
            "http",
        }

        for module_path in (project_root / "brain_ds" / "ui" / "cli.py", project_root / "brain_ds" / "ui" / "server.py"):
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            for node in ast.walk(tree):
                module_name = None
                if isinstance(node, ast.Import):
                    module_name = node.names[0].name
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        continue
                    if node.module is None:
                        continue
                    module_name = node.module

                if not module_name:
                    continue

                root = module_name.split(".", 1)[0]
                self.assertTrue(
                    root in allowed_roots or root == "brain_ds" or module_name.startswith("."),
                    f"Unexpected third-party import in {module_path.name}: {module_name}",
                )

    def test_threaded_runtime_serves_active_graph_with_render_context_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                store = GraphStore(str(store_path), allow_cross_thread=True)
                store.import_json(_valid_graph("Old Org", generated_at="2026-03-01T08:00:00Z"), workspace_root=str(root))
                time.sleep(1.1)
                store.import_json(_valid_graph("New Org", generated_at="2026-03-02T08:00:00Z"), workspace_root=str(root))

                runtime = server.ServerRuntime(project_root=root, store=store)
                active_graph, _ = runtime._active_graph_payload()
                self.assertEqual(active_graph.org, "New Org")

                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), runtime.handler_class())
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                with urlopen(f"http://127.0.0.1:{httpd.server_port}/", timeout=2) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("RENDER_CONTEXT", body)
                    self.assertIn('"contract_version": "1.0.0"', body)
                with urlopen(f"http://127.0.0.1:{httpd.server_port}/api/graphs", timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 200)
                    self.assertEqual(len(payload), 2)
            finally:
                if "httpd" in locals():
                    httpd.shutdown()
                    thread.join(timeout=2)
                    httpd.server_close()
                if "store" in locals():
                    store.close()
