from __future__ import annotations

import sys
import unittest
import json
import os
import io
import shutil
import subprocess
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui import cli
from brain_ds.store.graph_store import GraphStore


class MCPClaudeConfigTests(unittest.TestCase):
    def _create_store_fixture(self, root: Path) -> None:
        store_dir = root / ".brain_ds"
        store_dir.mkdir(parents=True)
        store = GraphStore(str(store_dir / "store.db"))
        store.close()

    def test_generate_claude_config_shape(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            config = generate_claude_config(Path("."))

        server = config["mcpServers"]["brain_ds"]
        self.assertEqual(server["type"], "stdio")
        self.assertTrue(os.path.isabs(server["command"]))
        self.assertTrue(server["command"].replace("\\", "/").endswith("fake/bin/brain_ds"))
        self.assertEqual(server["args"], ["mcp", "--project-root", "."])
        self.assertEqual(server["env"], {"BRAIN_DS_PROJECT_ROOT": "."})

    def test_generate_claude_config_absolute_flag(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            config = generate_claude_config(Path("."), absolute=True)

        root_value = config["mcpServers"]["brain_ds"]["args"][2]
        self.assertTrue(os.path.isabs(root_value))
        self.assertEqual(config["mcpServers"]["brain_ds"]["env"]["BRAIN_DS_PROJECT_ROOT"], root_value)

    def test_generate_claude_config_normalizes_relative_windows_dot_command(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value=r".\brain_ds.CMD"):
            config = generate_claude_config(Path("."), absolute=True)

        command = config["mcpServers"]["brain_ds"]["command"]
        self.assertTrue(os.path.isabs(command))

    def test_generate_claude_config_normalizes_bare_relative_command(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="brain_ds.CMD"):
            config = generate_claude_config(Path("."))

        command = config["mcpServers"]["brain_ds"]["command"]
        self.assertTrue(os.path.isabs(command))

    def test_generate_claude_config_raises_when_not_on_path(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "PATH"):
                generate_claude_config(Path("."))

    def test_generate_claude_config_json_roundtrip(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="C:/tools/brain_ds.exe"):
            config = generate_claude_config(Path("C:/Users/dev/project"))

        encoded = json.dumps(config)
        decoded = json.loads(encoded)
        self.assertEqual(decoded, config)

    def test_print_config_cli_outputs_valid_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(["mcp", "print-config", "--project-root", "."])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("mcpServers", payload)
        self.assertIn("brain_ds", payload["mcpServers"])

    def test_print_config_missing_project_root_uses_default(self) -> None:
        stdout = io.StringIO()

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            with redirect_stdout(stdout):
                code = cli.main(["mcp", "print-config"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mcpServers"]["brain_ds"]["args"][2], ".")

    def test_print_config_empty_project_root_exits_nonzero(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["mcp", "print-config", "--project-root", ""])

        self.assertNotEqual(code, 0)

    def test_print_config_nonexistent_root_exits_nonzero(self) -> None:
        missing = "definitely-missing-folder-xyz"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["mcp", "print-config", "--project-root", missing])

        self.assertNotEqual(code, 0)
        self.assertIn(missing, stderr.getvalue())

    def test_print_config_binary_not_on_path_exits_nonzero(self) -> None:
        stderr = io.StringIO()

        with patch("brain_ds.mcp.config.shutil.which", return_value=None):
            with redirect_stderr(stderr):
                code = cli.main(["mcp", "print-config", "--project-root", "."])

        self.assertNotEqual(code, 0)
        self.assertIn("PATH", stderr.getvalue())

    def test_print_config_no_global_path_construction(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        targets = [
            project_root / "brain_ds" / "mcp" / "config.py",
            project_root / "brain_ds" / "ui" / "cli.py",
        ]
        forbidden = ["~/.claude", "expanduser", ".claude/settings.json", "os.path.expanduser"]

        for target in targets:
            content = target.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, content)

    def test_config_handshake_with_mcp_server(self) -> None:
        from brain_ds.mcp.config import generate_claude_config

        with self.subTest("with_store_fixture"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._create_store_fixture(root)
                config = generate_claude_config(root, absolute=True)

                server = config["mcpServers"]["brain_ds"]
                args = server["args"]
                env = os.environ.copy()
                env.update(server["env"])

                requests = [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "t", "version": "1"},
                        },
                    },
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                ]
                payload = "\n".join(json.dumps(item) for item in requests) + "\n"

                proc = subprocess.run([sys.executable, "-m", "brain_ds", *args], input=payload, text=True, capture_output=True, env=env, check=False)
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)

                lines = [line for line in proc.stdout.splitlines() if line.strip()]
                self.assertEqual(len(lines), 2)
                initialize_response = json.loads(lines[0])
                tools_response = json.loads(lines[1])

                self.assertEqual(initialize_response["result"]["protocolVersion"], "2024-11-05")
                tools = tools_response["result"]["tools"]
                self.assertEqual(len(tools), 17)

    def test_claude_md_contains_required_sections(self) -> None:
        claude_path = Path(__file__).resolve().parents[1] / "CLAUDE.md"
        content = claude_path.read_text(encoding="utf-8")

        required_markers = [
            "2024-11-05",
            "mcpServers",
            "print-config",
            "/mcp",
            "list_nodes",
            "get_node",
            "search_graph",
            "update_node",
            "add_edge",
            "delete_node",
            "delete_edge",
            "run_elicit",
            "map_connections",
            "generate_brd",
            "list_graphs",
            "create_graph",
            "import_graph",
            "list_data_sources",
        ]
        for marker in required_markers:
            self.assertIn(marker, content)


if __name__ == "__main__":
    unittest.main()
