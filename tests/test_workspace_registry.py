"""Workspace scoping tests: global registry, MCP tools, grounding context."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import brain_ds.workspaces as workspaces
from brain_ds.store.graph_store import GraphStore


def _make_store(root: Path, graph_id: str = "g-1") -> Path:
    store_dir = root / ".brain_ds"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "store.db"
    store = GraphStore(str(db_path))
    try:
        store.create_graph(graph_id, name=f"Org {graph_id}")
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


class WorkspaceRegistryTests(RegistryHomeMixin):
    def test_register_and_list_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = workspaces.register_workspace(tmp, name="Demo")

            listed = workspaces.list_workspaces()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["name"], "Demo")
            self.assertEqual(listed[0]["path"], entry["path"])
            self.assertFalse(listed[0]["store_exists"])

    def test_register_same_path_updates_instead_of_duplicating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspaces.register_workspace(tmp)
            workspaces.register_workspace(tmp, name="Renamed")

            listed = workspaces.list_workspaces()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["name"], "Renamed")

    def test_list_marks_store_exists_for_initialized_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_store(root)
            workspaces.register_workspace(root)

            listed = workspaces.list_workspaces()
            self.assertTrue(listed[0]["store_exists"])

    def test_find_workspace_matches_normalized_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspaces.register_workspace(tmp)
            self.assertIsNotNone(workspaces.find_workspace(tmp))
            self.assertIsNone(workspaces.find_workspace(tmp + "-missing"))

    def test_corrupt_registry_degrades_to_empty(self) -> None:
        registry = workspaces.registry_path()
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("{not json", encoding="utf-8")

        self.assertEqual(workspaces.list_workspaces(), [])

    def test_project_root_from_store_path_strips_brain_ds_dir(self) -> None:
        root = workspaces.project_root_from_store_path(r"C:\proj\.brain_ds\store.db")
        self.assertEqual(root.name, "proj")


class ListWorkspacesToolTests(RegistryHomeMixin):
    def test_list_workspaces_tool_marks_active_workspace(self) -> None:
        from brain_ds.mcp.tools import list_workspaces as list_workspaces_tool

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a).resolve(), Path(tmp_b).resolve()
            db_a = _make_store(root_a, "g-a")
            _make_store(root_b, "g-b")
            workspaces.register_workspace(root_a)
            workspaces.register_workspace(root_b)

            store = GraphStore(str(db_a))
            try:
                result = list_workspaces_tool(store, {})
            finally:
                store.close()

        self.assertEqual(result["active_project_root"], str(root_a))
        self.assertTrue(result["active_registered"])
        flags = {entry["path"]: entry["active"] for entry in result["workspaces"]}
        self.assertTrue(flags[str(root_a)])
        self.assertFalse(flags[str(root_b)])

    def test_open_workspace_direct_handler_is_rejected(self) -> None:
        from brain_ds.mcp.tools import open_workspace as open_workspace_tool

        with tempfile.TemporaryDirectory() as tmp:
            db = _make_store(Path(tmp))
            store = GraphStore(str(db))
            try:
                result = open_workspace_tool(store, {"path": tmp})
            finally:
                store.close()

        self.assertEqual(result["code"], -32000)
        self.assertIn("server session", result["message"])


class OpenWorkspaceServerTests(RegistryHomeMixin):
    def _run_server(self, root: Path, requests: list[dict]) -> list[dict]:
        from brain_ds.mcp.server import run_mcp_server

        stdin = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
        stdout = io.StringIO()
        with patch("brain_ds.mcp.server.sys.stdin", stdin), patch("brain_ds.mcp.server.sys.stdout", stdout):
            run_mcp_server(root)
        return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]

    def test_open_workspace_switches_active_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a).resolve(), Path(tmp_b).resolve()
            _make_store(root_a, "g-a")
            _make_store(root_b, "g-b")
            workspaces.register_workspace(root_b)

            responses = self._run_server(
                root_a,
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "open_workspace", "arguments": {"path": str(root_b)}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_graphs", "arguments": {}}},
                ],
            )

        open_payload = json.loads(responses[0]["result"]["content"][0]["text"])
        self.assertEqual(open_payload["project_root"], str(root_b))
        self.assertEqual([g["id"] for g in open_payload["graphs"]], ["g-b"])

        graphs_payload = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual([g["id"] for g in graphs_payload], ["g-b"])

    def test_open_workspace_rejects_unregistered_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a).resolve(), Path(tmp_b).resolve()
            _make_store(root_a, "g-a")
            _make_store(root_b, "g-b")

            responses = self._run_server(
                root_a,
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "open_workspace", "arguments": {"path": str(root_b)}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_graphs", "arguments": {}}},
                ],
            )

        self.assertIn("error", responses[0])
        self.assertIn("not registered", responses[0]["error"]["message"])
        # Active store must remain the original workspace after the rejection.
        graphs_payload = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual([g["id"] for g in graphs_payload], ["g-a"])

    def test_server_startup_registers_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            _make_store(root)

            self._run_server(root, [])

            self.assertIsNotNone(workspaces.find_workspace(root))

    def test_server_startup_does_not_register_fresh_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            self._run_server(root, [])

            self.assertIsNone(workspaces.find_workspace(root))


class GroundingWorkspaceContextTests(RegistryHomeMixin):
    def test_grounding_tools_attach_workspace_context(self) -> None:
        from brain_ds.mcp.tools import generate_brd, map_connections, run_elicit

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            db = _make_store(root)
            workspaces.register_workspace(root)

            store = GraphStore(str(db))
            try:
                for handler in (run_elicit, map_connections, generate_brd):
                    payload = handler(store, {})
                    workspace = payload["workspace"]
                    self.assertEqual(workspace["active_project_root"], str(root))
                    self.assertEqual([g["id"] for g in workspace["active_graphs"]], ["g-1"])
                    self.assertEqual(len(workspace["registered_workspaces"]), 1)
                    self.assertIn("mismatch_rule", workspace["protocol"])
            finally:
                store.close()

    def test_elicit_workflow_contains_completeness_gate(self) -> None:
        from brain_ds.mcp.grounding import ELICIT_WORKFLOW

        workflow = cast(dict[str, Any], ELICIT_WORKFLOW)
        steps = " ".join(cast(list[str], workflow["steps"]))
        self.assertIn("completeness gate", steps)
        self.assertIn("Never advance", steps)
        self.assertIn("no gaps", cast(str, workflow["completeness_gate"]))

    def test_workspace_protocol_requires_asking_on_mismatch(self) -> None:
        from brain_ds.mcp.grounding import WORKSPACE_PROTOCOL

        protocol = cast(dict[str, str], WORKSPACE_PROTOCOL)
        self.assertIn("open_workspace", protocol["mismatch_rule"])
        self.assertIn("ask the user", protocol["mismatch_rule"])
        self.assertIn("brain_ds setup", protocol["registration_rule"])


class SetupRegistersWorkspaceTests(RegistryHomeMixin):
    def test_apply_setup_registers_project_root(self) -> None:
        from brain_ds.ui.setup import apply_setup

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            apply_setup(root, agent="claude")

            entry = workspaces.find_workspace(root)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry["name"], root.name)


if __name__ == "__main__":
    unittest.main()
