import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.store.graph_store import GraphStore
from brain_ds.ui import cli
from brain_ds.ui.setup import paths_align, setup_main


class TestSetup(unittest.TestCase):
    def _fake_claude_config(self, project_root: Path) -> dict:
        root = str(project_root.resolve())
        return {
            "mcpServers": {
                "brain_ds": {
                    "type": "stdio",
                    "command": "C:/tools/brain_ds.exe",
                    "args": ["mcp", "--project-root", root],
                    "env": {"BRAIN_DS_PROJECT_ROOT": root},
                }
            }
        }

    def _fake_opencode_config(self, project_root: Path) -> dict:
        root = str(project_root.resolve())
        return {
            "mcp": {
                "brain_ds": {
                    "type": "local",
                    "command": ["C:/tools/brain_ds.exe", "mcp", "--project-root", root],
                    "environment": {"BRAIN_DS_PROJECT_ROOT": root},
                    "enabled": True,
                }
            }
        }

    def _run_setup(self, root: Path, *, agent: str = "both", dry_run: bool = False, force: bool = True) -> tuple[int, str]:
        stdout = io.StringIO()
        args = Namespace(project_root=str(root), agent=agent, dry_run=dry_run, force=force)
        with patch("brain_ds.ui.setup.generate_claude_config", side_effect=lambda project_root, absolute=True: self._fake_claude_config(project_root)):
            with patch("brain_ds.ui.setup.generate_opencode_config", side_effect=lambda project_root, absolute=True: self._fake_opencode_config(project_root)):
                with redirect_stdout(stdout):
                    code = setup_main(args)
        return code, stdout.getvalue()

    def test_setup_help_lists_all_flags(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(stdout):
            cli.main(["setup", "--help"])

        self.assertEqual(ctx.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("--project-root", help_text)
        self.assertIn("default: .", help_text)
        self.assertIn("--agent", help_text)
        self.assertIn("claude", help_text)
        self.assertIn("opencode", help_text)
        self.assertIn("both", help_text)
        self.assertIn("--dry-run", help_text)
        self.assertIn("--force", help_text)

    def test_setup_creates_store_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, _ = self._run_setup(root)

            self.assertEqual(code, 0)
            self.assertTrue((root / ".brain_ds" / "store.db").exists())

    def test_setup_non_destructive_to_existing_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True)
            store = GraphStore(str(store_path))
            store.close()
            before = store_path.read_bytes()

            code, _ = self._run_setup(root)

            self.assertEqual(code, 0)
            self.assertEqual(store_path.read_bytes(), before)

    def test_setup_merges_preserving_other_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_path = root / ".mcp.json"
            claude_path.write_text(
                json.dumps({"mcpServers": {"other": {"command": "keep-me"}}}, indent=2),
                encoding="utf-8",
            )

            code, _ = self._run_setup(root, agent="claude")

            self.assertEqual(code, 0)
            payload = json.loads(claude_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["mcpServers"]["other"], {"command": "keep-me"})
            self.assertIn("brain_ds", payload["mcpServers"])

    def test_setup_backs_up_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_path = root / ".mcp.json"
            original = {"mcpServers": {"other": {"command": "keep-me"}}}
            claude_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

            code, _ = self._run_setup(root, agent="claude")

            self.assertEqual(code, 0)
            backups = list(root.glob(".mcp.json*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), original)

    def test_setup_writes_absolute_root_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = Path.cwd()
            os.chdir(root)
            try:
                code, _ = self._run_setup(Path("."), agent="claude")
            finally:
                os.chdir(previous)

            self.assertEqual(code, 0)
            payload = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            server = payload["mcpServers"]["brain_ds"]
            self.assertEqual(server["args"][2], str(root.resolve()))
            self.assertEqual(server["env"]["BRAIN_DS_PROJECT_ROOT"], str(root.resolve()))

    def test_setup_writes_absolute_root_opencode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, _ = self._run_setup(root, agent="opencode")

            self.assertEqual(code, 0)
            payload = json.loads((root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
            server = payload["mcp"]["brain_ds"]
            self.assertEqual(server["command"][2], "--project-root")
            self.assertEqual(server["command"][3], str(root.resolve()))
            self.assertEqual(server["environment"]["BRAIN_DS_PROJECT_ROOT"], str(root.resolve()))

    def test_setup_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / ".brain_ds"
            store_dir.mkdir(parents=True)
            store_path = store_dir / "store.db"
            store_path.write_bytes(b"existing-store")
            claude_path = root / ".mcp.json"
            claude_original = {"mcpServers": {"other": {"command": "keep-me"}}}
            claude_path.write_text(json.dumps(claude_original, indent=2), encoding="utf-8")

            code, output = self._run_setup(root, agent="claude", dry_run=True)

            self.assertEqual(code, 0)
            self.assertEqual(store_path.read_bytes(), b"existing-store")
            self.assertEqual(json.loads(claude_path.read_text(encoding="utf-8")), claude_original)
            self.assertFalse((store_dir / "setup.json").exists())
            self.assertEqual(list(root.glob(".mcp.json*.bak")), [])
            self.assertIn("DRY RUN", output)
            self.assertIn(".mcp.json", output)

    def test_setup_force_no_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch("builtins.input", side_effect=AssertionError("input should not be called")):
                code, _ = self._run_setup(root, force=True)

            self.assertEqual(code, 0)

    def test_setup_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, _ = self._run_setup(root, agent="claude")

            self.assertEqual(code, 0)
            payload = json.loads((root / ".brain_ds" / "setup.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["project_root"], str(root.resolve()))
            self.assertEqual(payload["agents"], ["claude"])
            self.assertEqual(payload["version"], "0.1.0")
            self.assertIn("created_at", payload)

    def test_setup_idempotent_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first_code, _ = self._run_setup(root, agent="claude")
            second_code, _ = self._run_setup(root, agent="claude")

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            payload = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(payload["mcpServers"].keys()), ["brain_ds"])

    def test_setup_detects_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, output = self._run_setup(root, agent="both")

            self.assertEqual(code, 0)
            self.assertIn(".mcp.json", output)
            self.assertIn(".opencode/opencode.json", output)

    def test_path_canonicalization_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            self.assertTrue(paths_align(root, str(root)))

    def test_setup_checklist_emitted_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            code, output = self._run_setup(root)

            self.assertEqual(code, 0)
            first = output.index("1. Rebuild/install the Windows exe")
            second = output.index("2. Launch the desktop exe and pick this folder")
            third = output.index("3. Restart your agent client")
            fourth = output.index("4. Approve the brain_ds MCP server if prompted")
            self.assertTrue(first < second < third < fourth)


if __name__ == "__main__":
    unittest.main()
