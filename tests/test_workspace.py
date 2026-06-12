import os
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_ds.ontology import Graph
from brain_ds.ui.render_context import WorkspaceContext, _compute_workspace_meta, build_render_context


class TestWorkspaceContext(unittest.TestCase):
    def test_workspace_context_has_project_display_and_store_paths(self):
        root = Path("/workspace")
        workspace = WorkspaceContext(
            project_root=root,
            display_path="acme/graph.json",
            store_path=root / ".brain_ds" / "store.db",
        )

        self.assertIsInstance(workspace.project_root, Path)
        self.assertEqual(workspace.display_path, "acme/graph.json")
        self.assertIsInstance(workspace.store_path, Path)

    @unittest.skipUnless(os.name == "nt", "asserts Windows drive-letter path semantics")
    def test_windows_display_path_uses_forward_slashes_and_store_path_uses_hidden_dir(self):
        workspace = WorkspaceContext.from_root_and_graph(
            Path("C:/workspace"),
            Path("C:/workspace/acme-corp/billing/v2-graph.json"),
        )

        self.assertEqual(workspace.display_path, "acme-corp/billing/v2-graph.json")
        self.assertEqual(workspace.store_path, Path("C:/workspace/.brain_ds/store.db"))
        self.assertNotIn("\\", workspace.display_path)

    def test_compute_workspace_meta_uses_workspace_fields_without_cwd_fallback(self):
        workspace = WorkspaceContext.from_root_and_graph(
            Path("/workspace"),
            Path("/workspace/acme-corp/v2-graph.json"),
        )

        with patch("brain_ds.ui.render_context.Path.cwd", side_effect=AssertionError("Path.cwd must not be called")):
            meta = _compute_workspace_meta(workspace)

        self.assertEqual(meta["root"], str(workspace.project_root.resolve()))
        self.assertEqual(meta["displayPath"], "acme-corp/v2-graph.json")

    def test_build_render_context_without_workspace_has_no_cwd_dependency(self):
        graph = Graph.from_v1({"nodes": [], "edges": []})

        with patch("brain_ds.ui.render_context.Path.cwd", side_effect=AssertionError("Path.cwd must not be called")):
            context = build_render_context(graph)

        self.assertEqual(context["meta"]["workspace"]["project"], "default")
