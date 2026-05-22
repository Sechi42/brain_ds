import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path


def _valid_graph(org: str) -> dict:
    return {
        "org": org,
        "generated_at": "2026-03-01T08:00:00Z",
        "nodes": [{"id": "n1", "label": f"{org} Node", "type": "Department"}],
        "edges": [],
        "evidence": [],
    }


class TestProjectScanner(unittest.TestCase):
    def test_depth_1_scanner_imports_root_and_brain_ds_and_skips_nested(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "root.json").write_text(json.dumps(_valid_graph("Root Org")), encoding="utf-8")
            workspace_dir = root / ".brain_ds"
            workspace_dir.mkdir(parents=True)
            (workspace_dir / "workspace.json").write_text(json.dumps(_valid_graph("Workspace Org")), encoding="utf-8")
            nested = root / "src"
            nested.mkdir(parents=True)
            (nested / "nested.json").write_text(json.dumps(_valid_graph("Nested Org")), encoding="utf-8")

            imported_ids = server.scan_project_root(project_root=root)

            self.assertEqual(len(imported_ids), 2)
            self.assertTrue((root / ".brain_ds" / "store.db").exists())

            from brain_ds.store.graph_store import GraphStore

            store = GraphStore(str(root / ".brain_ds" / "store.db"), read_only=True)
            try:
                labels = {meta.org for meta in store.list_graphs()}
            finally:
                store.close()

            self.assertIn("Root Org", labels)
            self.assertIn("Workspace Org", labels)
            self.assertNotIn("Nested Org", labels)

    def test_invalid_json_is_logged_and_skipped(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "invalid.json").write_text("{bad", encoding="utf-8")
            (root / "valid.json").write_text(json.dumps(_valid_graph("Valid Org")), encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                imported_ids = server.scan_project_root(project_root=root)

            self.assertEqual(len(imported_ids), 1)
            self.assertIn("Skipping invalid graph JSON", stderr.getvalue())
