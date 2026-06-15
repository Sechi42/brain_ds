from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from brain_ds.store.graph_store import GraphStore
from brain_ds.ui import cli


class MCPServerCliTests(unittest.TestCase):
    def test_mcp_falls_back_to_cwd_when_flag_and_env_missing(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict("os.environ"):
                    os.environ.pop("BRAIN_DS_PROJECT_ROOT", None)
                    with patch("brain_ds.ui.cli.run_mcp_server") as run_mcp_server:
                        code = cli.main(["mcp"])
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(code, 0)
        run_mcp_server.assert_called_once_with(root)

    def test_mcp_dispatches_to_server_with_explicit_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("brain_ds.ui.cli.run_mcp_server") as run_mcp_server:
                code = cli.main(["mcp", "--project-root", str(root)])

        self.assertEqual(code, 0)
        run_mcp_server.assert_called_once_with(root.resolve())

    def test_mcp_uses_env_var_project_root_when_flag_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict("os.environ", {"BRAIN_DS_PROJECT_ROOT": str(root)}, clear=False):
                with patch("brain_ds.ui.cli.run_mcp_server") as run_mcp_server:
                    code = cli.main(["mcp"])

        self.assertEqual(code, 0)
        run_mcp_server.assert_called_once_with(root.resolve())

    def test_mcp_invalid_project_root_exits_2_without_traceback(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["mcp", "--project-root", "missing-folder-xyz"])

        self.assertEqual(code, 2)
        output = stderr.getvalue()
        self.assertIn("Error:", output)
        self.assertNotIn("Traceback", output)


class MCPServerLifecycleTests(unittest.TestCase):
    def test_cli_mcp_uses_standard_env_lookup_without_dynamic_import(self) -> None:
        import inspect

        source = inspect.getsource(cli)
        self.assertNotIn('__import__("os")', source)

    def test_pyproject_does_not_pin_unused_mcp_sdk_dependency(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        self.assertNotIn('"mcp>=1.0.0,<2.0.0"', content)

    def _create_store_fixture(self, root: Path) -> str:
        store_dir = root / ".brain_ds"
        store_dir.mkdir(parents=True)
        db_path = store_dir / "store.db"
        store = GraphStore(str(db_path))
        try:
            graph_id = "graph-server"
            store.meta_repo.save_graph_meta(
                graph_id=graph_id,
                workspace_root=str(root),
                workspace_path=str(root),
                project="project-server",
                org="org-server",
                schema_version="2.0.0",
                contract_version="1.0.0",
                node_count=0,
                edge_count=0,
                imported_from=None,
                generated_at="",
            )
            store.upsert_node(
                graph_id,
                {
                    "id": "N-1",
                    "label": "Alpha Task",
                    "type": "Task",
                    "supertype": "Work",
                    "parent_id": "ROOT",
                    "details": {"summary": "Fixture"},
                },
            )
        finally:
            store.close()
        return graph_id

    def test_run_mcp_server_parses_malformed_json_without_traceback(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_store_fixture(root)

            stdin = io.StringIO("{bad json\n")
            stdout = io.StringIO()

            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            payload = json.loads(stdout.getvalue().strip())
            self.assertEqual(payload["error"]["code"], -32700)
            self.assertNotIn("Traceback", stdout.getvalue())

    def test_run_mcp_server_initialize_and_tools_list(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_store_fixture(root)

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            stdin = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
            stdout = io.StringIO()

            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            initialize_response = json.loads(lines[0])
            tools_response = json.loads(lines[1])

            self.assertIn("capabilities", initialize_response["result"])
            tools = tools_response["result"]["tools"]
            self.assertEqual(len(tools), 22)
            self.assertTrue(all("inputSchema" in tool for tool in tools))

    def test_run_mcp_server_tools_call_dispatches_read_tool(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_id = self._create_store_fixture(root)

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_nodes", "arguments": {"graph_id": graph_id}},
                },
            ]

            stdin = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
            stdout = io.StringIO()
            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            call_response = json.loads(lines[1])
            self.assertIn("result", call_response)
            self.assertEqual(call_response["result"]["content"][0]["type"], "text")
            result_payload = json.loads(call_response["result"]["content"][0]["text"])
            self.assertEqual(len(result_payload), 1)
            self.assertEqual(result_payload[0]["id"], "N-1")

    def test_run_mcp_server_map_connections_survives_cp1252_stdout(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        class _NarrowStdout:
            """write/flush only — no reconfigure, encodes cp1252 like a legacy Windows console."""

            def __init__(self) -> None:
                self.buffer = io.BytesIO()
                self._wrapper = io.TextIOWrapper(self.buffer, encoding="cp1252", newline="")

            def write(self, text: str) -> int:
                return self._wrapper.write(text)

            def flush(self) -> None:
                self._wrapper.flush()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_store_fixture(root)

            request = {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {"name": "map_connections", "arguments": {}},
            }
            stdin = io.StringIO(json.dumps(request) + "\n")
            stdout = _NarrowStdout()
            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            raw = stdout.buffer.getvalue().decode("cp1252")
            payload = json.loads(raw.strip())
            self.assertIn("result", payload)
            context = json.loads(payload["result"]["content"][0]["text"])
            self.assertIn("connection_rules", context)

    def test_run_mcp_server_tools_call_unknown_tool_returns_safe_error(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_store_fixture(root)

            request = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "missing_tool", "arguments": {}},
            }
            stdin = io.StringIO(json.dumps(request) + "\n")
            stdout = io.StringIO()
            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            payload = json.loads(stdout.getvalue().strip())
            self.assertEqual(payload["error"]["code"], -32601)
            self.assertIn("Unknown tool", payload["error"]["message"])
            self.assertNotIn("Traceback", stdout.getvalue())

    def test_run_mcp_server_tools_call_invalid_params_returns_validation_error(self) -> None:
        from brain_ds.mcp.server import run_mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_store_fixture(root)

            request = {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "list_nodes", "arguments": {}},
            }
            stdin = io.StringIO(json.dumps(request) + "\n")
            stdout = io.StringIO()
            with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
                run_mcp_server(root)

            payload = json.loads(stdout.getvalue().strip())
            self.assertEqual(payload["error"]["code"], -32602)
            self.assertIn("Missing required parameter: graph_id", payload["error"]["message"])
            self.assertNotIn("Traceback", stdout.getvalue())

if __name__ == "__main__":
    unittest.main()
