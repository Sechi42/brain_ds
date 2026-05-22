import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui import cli


class TestCliServe(unittest.TestCase):
    def test_ui_without_graph_json_invokes_run_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("brain_ds.ui.cli.run_server") as run_server:
                code = cli.main(["ui", "--project-root", str(root)])

        self.assertEqual(code, 0)
        run_server.assert_called_once_with(project_root=root.resolve(), port=8765)

    def test_ui_serve_with_custom_port_invokes_run_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("brain_ds.ui.cli.run_server") as run_server:
                code = cli.main(["ui", "serve", "--port", "9000", "--project-root", str(root)])

        self.assertEqual(code, 0)
        run_server.assert_called_once_with(project_root=root.resolve(), port=9000)

    def test_ui_with_graph_json_preserves_legacy_static_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path = root / "graph.json"
            graph_path.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
            with patch("brain_ds.ui.cli.run_server") as run_server, patch(
                "brain_ds.ui.cli.render_graph_file", return_value=root / "viewer.html"
            ) as render_graph_file:
                code = cli.main(["ui", str(graph_path), "--project-root", str(root)])

        self.assertEqual(code, 0)
        run_server.assert_not_called()
        render_graph_file.assert_called_once()
