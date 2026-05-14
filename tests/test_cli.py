import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui import cli


class TestCli(unittest.TestCase):
    def test_bare_command_prints_help_and_fails(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main([])

        self.assertEqual(code, 2)
        self.assertIn("usage: brain_ds", stderr.getvalue())

    def test_ui_help_prints_usage(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(stdout):
            cli.main(["ui", "--help"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage: brain_ds ui", stdout.getvalue())
        self.assertIn("--output", stdout.getvalue())
        self.assertIn("--open", stdout.getvalue())
        self.assertIn("--simple", stdout.getvalue())

    def test_custom_output_passed_to_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "nested" / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--output", str(output_path)])

            self.assertEqual(code, 0)
            render_mock.assert_called_once_with(
                graph_path.resolve(),
                output_path=output_path.resolve(),
                open_browser=False,
                simple=False,
            )

    def test_open_flag_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path):
                code = cli.main(["ui", str(graph_path), "--open"])

            self.assertEqual(code, 0)

    def test_open_flag_fallback_still_success_when_renderer_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path):
                code = cli.main(["ui", str(graph_path), "--open"])

            self.assertEqual(code, 0)

    def test_missing_file_returns_2(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["ui", "missing.json"])

        self.assertEqual(code, 2)
        self.assertIn("Error: file not found:", stderr.getvalue())

    def test_invalid_json_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "bad.json"
            graph_path.write_text("{bad-json", encoding="utf-8")

            with patch(
                "brain_ds.ui.cli.render_graph_file",
                side_effect=json.JSONDecodeError("Expecting value", "{", 1),
            ):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code = cli.main(["ui", str(graph_path)])

            self.assertEqual(code, 2)
            self.assertIn("Error: invalid JSON -", stderr.getvalue())

    def test_simple_flag_passed_to_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--simple"])

            self.assertEqual(code, 0)
            render_mock.assert_called_once_with(
                graph_path.resolve(),
                output_path=None,
                open_browser=False,
                simple=True,
            )

    def test_default_mode_routes_to_interactive_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path)])

            self.assertEqual(code, 0)
            self.assertEqual(render_mock.call_args.kwargs["simple"], False)

    def test_simple_mode_allows_open_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--simple", "--open"])

            self.assertEqual(code, 0)
            render_mock.assert_called_once_with(
                graph_path.resolve(),
                output_path=None,
                open_browser=True,
                simple=True,
            )

    def test_missing_pyvis_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")

            with patch("brain_ds.ui.cli.render_graph_file", side_effect=RuntimeError):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code = cli.main(["ui", str(graph_path), "--simple"])

            self.assertEqual(code, 1)
            self.assertIn("Error: pyvis not installed. Run: uv sync --extra simple", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
