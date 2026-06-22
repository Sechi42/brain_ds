from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import brain_ds.workspaces as workspaces


class WorkspaceRegistryPruneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        self._env = patch.dict("os.environ", {"BRAIN_DS_HOME": self._home.name})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(self._home.cleanup)

    def test_list_workspaces_prunes_duplicate_and_deleted_temp_entries(self) -> None:
        with tempfile.TemporaryDirectory() as live_tmp:
            live_root = Path(live_tmp).resolve()
            deleted_root = Path(tempfile.mkdtemp(prefix="brain-ds-deleted-workspace-")).resolve()
            deleted_root.rmdir()
            payload = {
                "version": 1,
                "workspaces": [
                    {"path": str(deleted_root), "name": "Deleted", "registered_at": "old", "last_opened_at": "old"},
                    {"path": str(live_root), "name": "Old", "registered_at": "old", "last_opened_at": "old"},
                    {"path": str(live_root), "name": "New", "registered_at": "new", "last_opened_at": "new"},
                ],
            }
            registry = workspaces.registry_path()
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(json.dumps(payload), encoding="utf-8")

            listed = workspaces.list_workspaces()
            persisted = json.loads(registry.read_text(encoding="utf-8"))["workspaces"]

        self.assertEqual([entry["path"] for entry in listed], [str(live_root)])
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["name"], "New")
