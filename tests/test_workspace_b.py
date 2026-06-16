from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from fastapi.testclient import TestClient

import brain_ds.workspaces as workspaces
from brain_ds.store.graph_store import GraphStore


def _make_store(root: Path) -> Path:
    store_dir = root / ".brain_ds"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "store.db"
    store = GraphStore(str(db_path), allow_cross_thread=True)
    try:
        store.create_graph("g-1", name="Demo Org")
    finally:
        store.close()
    return db_path


class RegistryHomeMixin(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._home = tempfile.TemporaryDirectory()
        self._env = patch.dict("os.environ", {"BRAIN_DS_HOME": self._home.name})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(self._home.cleanup)


class WorkspaceRemovalTests(RegistryHomeMixin):
    def test_unregister_workspace_removes_registry_entry_but_leaves_store_db_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            store_db = _make_store(root)
            workspaces.register_workspace(root)

            workspaces.unregister_workspace(root)

            self.assertIsNone(workspaces.find_workspace(root))
            self.assertTrue(store_db.exists())

    def test_unregister_workspace_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as registered, tempfile.TemporaryDirectory() as missing:
            registered_root = Path(registered).resolve()
            missing_root = Path(missing).resolve()
            workspaces.register_workspace(registered_root)

            workspaces.unregister_workspace(missing_root)

            self.assertIsNotNone(workspaces.find_workspace(registered_root))
            self.assertIsNone(workspaces.find_workspace(missing_root))

    def test_delete_workspace_store_deletes_store_db_when_called_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            store_db = _make_store(root)

            workspaces.delete_workspace_store(root, confirm_token=root.name)

            self.assertFalse(store_db.exists())


class WorkspaceDeleteEndpointTests(RegistryHomeMixin):
    def _client(self, root: Path) -> tuple[TestClient, GraphStore]:
        store_db = root / ".brain_ds" / "store.db"
        store_db.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(str(store_db), allow_cross_thread=True)
        from brain_ds.ui import server

        app = server.build_ui_app(project_root=root, store=store)
        return TestClient(app), store

    def test_delete_workspace_endpoint_defaults_to_unregister_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            store_db = _make_store(root)
            workspaces.register_workspace(root)
            client, store = self._client(root)
            try:
                with client:
                    response = client.delete(f"/api/workspaces/{quote(str(root), safe='')}")

                self.assertEqual(response.status_code, 200)
                self.assertIsNone(workspaces.find_workspace(root))
                self.assertTrue(store_db.exists())
            finally:
                store.close()

    def test_delete_workspace_endpoint_blocks_destructive_path_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            store_db = _make_store(root)
            workspaces.register_workspace(root)
            client, store = self._client(root)
            try:
                with client:
                    response = client.request(
                        "DELETE",
                        f"/api/workspaces/{quote(str(root), safe='')}?delete_store=true",
                        json={},
                    )

                self.assertEqual(response.status_code, 422)
                self.assertIsNotNone(workspaces.find_workspace(root))
                self.assertTrue(store_db.exists())
            finally:
                store.close()

    def test_delete_workspace_endpoint_with_token_deletes_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            store_db = _make_store(root)
            workspaces.register_workspace(root)
            client, store = self._client(root)
            try:
                with client:
                    response = client.request(
                        "DELETE",
                        f"/api/workspaces/{quote(str(root), safe='')}?delete_store=true",
                        json={"typed_confirm": root.name},
                    )

                self.assertEqual(response.status_code, 200)
                self.assertIsNone(workspaces.find_workspace(root))
                self.assertFalse(store_db.exists())
            finally:
                store.close()


class WorkspacePickerUiTests(unittest.TestCase):
    def test_vault_picker_exposes_two_tier_safe_confirm_actions(self) -> None:
        from brain_ds.ui.template_renderer import render_vault_picker_html

        html = render_vault_picker_html([{"id": "workspace-1", "label": "Workspace One"}])

        self.assertIn("Remove from list", html)
        self.assertIn("Delete all data", html)
        self.assertIn("typed_confirm", html)
        self.assertIn("irreversible", html.lower())


if __name__ == "__main__":
    unittest.main()
