from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from brain_ds.store.graph_store import GraphStore
from brain_ds.ui import server


def _fake_claude_config(project_root: Path, absolute: bool = True) -> dict:
    root = str(project_root.resolve())
    return {"mcpServers": {"brain_ds": {"type": "stdio", "command": "brain_ds.exe", "args": ["mcp", "--project-root", root], "env": {}}}}


def _fake_opencode_config(project_root: Path, absolute: bool = True) -> dict:
    root = str(project_root.resolve())
    return {"mcp": {"brain_ds": {"type": "local", "command": ["brain_ds.exe", "mcp", "--project-root", root], "enabled": True}}}


class SetupMcpEndpointTests(unittest.TestCase):
    store: GraphStore | None = None

    def _client(self, root: Path) -> TestClient:
        store_dir = root / ".brain_ds"
        store_dir.mkdir(parents=True, exist_ok=True)
        self.store = GraphStore(str(store_dir / "store.db"), allow_cross_thread=True)
        app = server.build_ui_app(project_root=root, store=self.store)
        return TestClient(app)

    def _close_store(self) -> None:
        if self.store is not None:
            self.store.close()
            self.store = None

    def test_setup_mcp_writes_both_configs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("brain_ds.ui.setup.generate_claude_config", side_effect=_fake_claude_config), patch(
                "brain_ds.ui.setup.generate_opencode_config", side_effect=_fake_opencode_config
            ):
                with self._client(root) as client:
                    response = client.post("/api/setup-mcp", json={"agent": "both"})
                self._close_store()

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["agents"], ["claude", "opencode"])
            self.assertIn(".mcp.json", payload["written"])
            self.assertTrue((root / ".mcp.json").exists())
            self.assertTrue((root / ".opencode" / "opencode.json").exists())
            manifest = json.loads((root / ".brain_ds" / "setup.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["agents"], ["claude", "opencode"])

    def test_setup_mcp_preserves_unrelated_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"other": {"command": "keep-me"}}}), encoding="utf-8"
            )
            with patch("brain_ds.ui.setup.generate_claude_config", side_effect=_fake_claude_config), patch(
                "brain_ds.ui.setup.generate_opencode_config", side_effect=_fake_opencode_config
            ):
                with self._client(root) as client:
                    response = client.post("/api/setup-mcp", json={"agent": "claude"})
                self._close_store()

            self.assertEqual(response.status_code, 200)
            merged = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["mcpServers"]["other"], {"command": "keep-me"})
            self.assertIn("brain_ds", merged["mcpServers"])

    def test_setup_mcp_rejects_unknown_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self._client(root) as client:
                response = client.post("/api/setup-mcp", json={"agent": "cursor"})
            self._close_store()

            self.assertEqual(response.status_code, 400)

    def test_vault_picker_offers_mcp_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self._client(root) as client:
                response = client.get("/vault-picker")
            self._close_store()

            self.assertEqual(response.status_code, 200)
            self.assertIn("setup-mcp-btn", response.text)
            self.assertIn("/api/setup-mcp", response.text)


if __name__ == "__main__":
    unittest.main()
