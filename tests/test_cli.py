import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui import cli


class TestCli(unittest.TestCase):
    def test_cli_setup_dispatch(self):
        with patch("brain_ds.ui.cli._run_setup", return_value=0) as run_setup:
            code = cli.main(["setup", "--dry-run"])

        self.assertEqual(code, 0)
        run_setup.assert_called_once()
        args = run_setup.call_args.args[0]
        self.assertEqual(args.command, "setup")
        self.assertTrue(args.dry_run)

    def test_mcp_print_config_format_opencode_outputs_opencode_schema(self):
        stdout = io.StringIO()

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            with redirect_stdout(stdout):
                code = cli.main(["mcp", "print-config", "--project-root", ".", "--format", "opencode"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("mcp", payload)
        self.assertIn("brain_ds", payload["mcp"])

    def test_mcp_print_config_default_format_is_claude(self):
        stdout = io.StringIO()

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            with redirect_stdout(stdout):
                code = cli.main(["mcp", "print-config", "--project-root", "."])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("mcpServers", payload)
        server = payload["mcpServers"]["brain_ds"]
        self.assertEqual(server["type"], "stdio")
        self.assertTrue(Path(server["command"]).is_absolute())
        self.assertIsInstance(server["args"], list)
        self.assertTrue(all(isinstance(item, str) for item in server["args"]))
        self.assertIn("env", server)
        self.assertIn("BRAIN_DS_PROJECT_ROOT", server["env"])

    def test_mcp_print_config_invalid_format_exits_nonzero(self):
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(stderr):
            cli.main(["mcp", "print-config", "--project-root", ".", "--format", "invalid"])

        self.assertNotEqual(ctx.exception.code, 0)
        self.assertIn("claude", stderr.getvalue())
        self.assertIn("opencode", stderr.getvalue())

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
        self.assertIn("--force", stdout.getvalue())

    def test_custom_output_passed_to_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "nested" / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--output", str(output_path)])

            self.assertEqual(code, 0)
            render_mock.assert_called_once()
            self.assertEqual(render_mock.call_args.args[0], graph_path.resolve())
            self.assertEqual(render_mock.call_args.kwargs["output_path"], output_path.resolve())
            self.assertEqual(render_mock.call_args.kwargs["open_browser"], False)
            self.assertEqual(render_mock.call_args.kwargs["simple"], False)
            self.assertEqual(render_mock.call_args.kwargs["force"], False)
            self.assertEqual(render_mock.call_args.kwargs["workspace"].graph_path, str(graph_path.resolve()))

    def test_open_flag_success(self):
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
            render_mock.assert_called_once()
            self.assertEqual(render_mock.call_args.args[0], graph_path.resolve())
            self.assertEqual(render_mock.call_args.kwargs["output_path"], None)
            self.assertEqual(render_mock.call_args.kwargs["open_browser"], False)
            self.assertEqual(render_mock.call_args.kwargs["simple"], True)
            self.assertEqual(render_mock.call_args.kwargs["force"], False)
            self.assertEqual(render_mock.call_args.kwargs["workspace"].graph_path, str(graph_path.resolve()))

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
            render_mock.assert_called_once()
            self.assertEqual(render_mock.call_args.args[0], graph_path.resolve())
            self.assertEqual(render_mock.call_args.kwargs["output_path"], None)
            self.assertEqual(render_mock.call_args.kwargs["open_browser"], True)
            self.assertEqual(render_mock.call_args.kwargs["simple"], True)
            self.assertEqual(render_mock.call_args.kwargs["force"], False)
            self.assertEqual(render_mock.call_args.kwargs["workspace"].graph_path, str(graph_path.resolve()))

    def test_force_flag_passed_to_renderer_for_file_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--force"])

            self.assertEqual(code, 0)
            render_mock.assert_called_once()
            self.assertEqual(render_mock.call_args.args[0], graph_path.resolve())
            self.assertEqual(render_mock.call_args.kwargs["output_path"], None)
            self.assertEqual(render_mock.call_args.kwargs["open_browser"], False)
            self.assertEqual(render_mock.call_args.kwargs["simple"], False)
            self.assertEqual(render_mock.call_args.kwargs["force"], True)
            self.assertEqual(render_mock.call_args.kwargs["workspace"].graph_path, str(graph_path.resolve()))

    def test_ui_force_validation_error_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")

            stderr = io.StringIO()
            with patch("brain_ds.ui.cli.render_graph_file", side_effect=ValueError("Validation failed: broken")):
                with redirect_stderr(stderr):
                    code = cli.main(["ui", str(graph_path)])

            self.assertEqual(code, 1)
            self.assertIn("Validation failed", stderr.getvalue())

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

    def test_ui_dash_reads_stdin_and_calls_render_graph_data(self):
        stdin = io.StringIO('{"org":"PipeOrg","nodes":[],"edges":[]}')
        with patch("sys.stdin", stdin), patch("brain_ds.ui.cli.render_graph_data", return_value=Path("graph-output.html")) as render_mock:
            code = cli.main(["ui", "-"])

        self.assertEqual(code, 0)
        self.assertEqual(render_mock.call_args.args[0]["org"], "PipeOrg")
        self.assertEqual(render_mock.call_args.kwargs["force"], False)

    def test_ui_dash_force_flag_passed_to_render_graph_data(self):
        stdin = io.StringIO('{"org":"PipeOrg","nodes":[],"edges":[]}')
        with patch("sys.stdin", stdin), patch("brain_ds.ui.cli.render_graph_data", return_value=Path("graph-output.html")) as render_mock:
            code = cli.main(["ui", "-", "--force"])

        self.assertEqual(code, 0)
        self.assertEqual(render_mock.call_args.kwargs["force"], True)

    def test_ui_root_flag_is_forwarded_into_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
            output_path = tmp_path / "viewer.html"
            root_path = tmp_path / "workspace-root"
            root_path.mkdir(parents=True)

            with patch("brain_ds.ui.cli.render_graph_file", return_value=output_path) as render_mock:
                code = cli.main(["ui", str(graph_path), "--root", str(root_path)])

            self.assertEqual(code, 0)
            self.assertEqual(render_mock.call_args.kwargs["workspace"].root, str(root_path.resolve()))

    def test_ui_serve_respects_env_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_root = Path(tmp) / "env-root"
            env_root.mkdir(parents=True)

            with patch.dict("os.environ", {"BRAIN_DS_PROJECT_ROOT": str(env_root)}, clear=False):
                with patch("brain_ds.ui.cli.run_server") as run_server:
                    code = cli.main(["ui", "serve"])

            self.assertEqual(code, 0)
            run_server.assert_called_once_with(project_root=env_root.resolve(), port=8765)

    def test_ui_serve_env_empty_falls_to_cwd(self):
        expected_root = Path(os.getcwd()).resolve()

        with patch.dict("os.environ", {"BRAIN_DS_PROJECT_ROOT": ""}, clear=False):
            with patch("brain_ds.ui.cli.run_server") as run_server:
                code = cli.main(["ui", "serve"])

        self.assertEqual(code, 0)
        run_server.assert_called_once_with(project_root=expected_root, port=8765)

    def test_ui_dash_output_dash_writes_html_to_stdout(self):
        stdin = io.StringIO('{"org":"PipeOrg","nodes":[],"edges":[]}')
        stdout = io.StringIO()
        with patch("sys.stdin", stdin), patch("brain_ds.ui.cli.render_graph_data", return_value="-"):
            with redirect_stdout(stdout):
                code = cli.main(["ui", "-", "--output", "-"])

        self.assertEqual(code, 0)
        self.assertIn("HTML viewer generated: -", stdout.getvalue())

    def test_ui_open_with_stdout_dash_exits_2_before_stdin_read(self):
        stdin = io.StringIO('{"org":"PipeOrg","nodes":[],"edges":[]}')
        stderr = io.StringIO()
        with patch("sys.stdin", stdin), redirect_stderr(stderr):
            code = cli.main(["ui", "-", "--open", "--output", "-"])

        self.assertEqual(code, 2)
        self.assertIn("cannot use --open with --output -", stderr.getvalue())
        self.assertEqual(stdin.tell(), 0)

    def test_ui_dash_with_malformed_json_stdin_exits_2(self):
        stdin = io.StringIO('{"org":')
        stderr = io.StringIO()
        with patch("sys.stdin", stdin), redirect_stderr(stderr):
            code = cli.main(["ui", "-"])

        self.assertEqual(code, 2)
        self.assertIn("Error: invalid JSON from stdin", stderr.getvalue())

    def test_ui_dash_with_non_utf8_stdin_exits_2(self):
        class _BinaryStdin:
            def read(self):
                return b"\xff\xfe\xfd"

        stderr = io.StringIO()
        with patch("sys.stdin", _BinaryStdin()), redirect_stderr(stderr):
            code = cli.main(["ui", "-"])

        self.assertEqual(code, 2)
        self.assertIn("Error: invalid UTF-8 from stdin", stderr.getvalue())

    def test_validate_help_prints_usage(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(stdout):
            cli.main(["validate", "--help"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage: brain_ds validate", stdout.getvalue())
        self.assertIn("--fix", stdout.getvalue())
        self.assertIn("safely normalized", stdout.getvalue())

    def test_validate_valid_graph_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "valid.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "Acme",
                        "nodes": [{"id": "n1", "label": "Node 1", "type": "Organization"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = cli.main(["validate", str(graph_path)])

            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")

    def test_validate_invalid_graph_exits_1_and_prints_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "invalid.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "Acme",
                        "nodes": [{"id": "n1", "label": "Node 1", "type": "Company"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = cli.main(["validate", str(graph_path)])

            self.assertEqual(code, 1)
            output = stderr.getvalue()
            self.assertIn("nodes[0].type", output)
            self.assertIn("Unsupported entity type", output)
            self.assertIn("Did you mean 'Organization'?", output)

    def test_validate_fix_prints_normalized_json_to_stdout_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "fixable.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "Acme",
                        "nodes": [{"id": "n1", "label": "Node 1", "type": "department"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(["validate", str(graph_path), "--fix"])

            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            normalized = json.loads(stdout.getvalue())
            self.assertEqual(normalized["nodes"][0]["type"], "Department")

    def test_validate_missing_file_returns_2(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["validate", "missing.json"])

        self.assertEqual(code, 2)
        self.assertIn("Error: file not found:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
