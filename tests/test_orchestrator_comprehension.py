from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from typing import Any, cast

from brain_ds.mcp.grounding import build_relationship_labels
from brain_ds.mcp.tools import add_edge, create_graph, list_graphs, search_graph, update_node
from brain_ds.ontology.entity_types import EntityType
from brain_ds.store.graph_store import GraphStore


class TestOrchestratorComprehension(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = GraphStore(str(Path(self.temp_dir.name) / "store.db"))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_fixed_five_op_script_passes_three_runs(self) -> None:
        for run in range(3):
            graph_id = f"graph-{run}"
            node_id = f"node-{run}"
            graphs_result = cast(list[dict[str, Any]], list_graphs(self.store, {}))
            create_result = create_graph(self.store, {"graph_id": graph_id, "name": f"Graph {run}"})
            update_result = update_node(
                self.store,
                {
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "label": f"Node {run}",
                    "type": EntityType.DEPARTMENT.value,
                    "card_sections": [{"title": "Overview", "content": "Live", "icon": "", "order": 1}],
                },
            )
            edge_result = add_edge(
                self.store,
                {
                    "graph_id": graph_id,
                    "source": node_id,
                    "target": node_id,
                    "label": build_relationship_labels()[0],
                },
            )
            search_result = cast(
                list[dict[str, Any]],
                search_graph(self.store, {"graph_id": graph_id, "query": f"node {run}"}),
            )

            self.assertEqual(len((graphs_result, create_result, update_result, edge_result, search_result)), 5)
            self.assertNotIn("code", create_result)
            self.assertEqual(cast(list[dict[str, Any]], update_result["card_sections"])[0]["content"], "Live")
            self.assertEqual(edge_result["label"], build_relationship_labels()[0])
            self.assertEqual(search_result[0]["id"], node_id)

    def test_body_key_regression_names_wrong_key_and_correct_key(self) -> None:
        create_graph(self.store, {"graph_id": "graph-regression", "name": "Regression"})

        result = update_node(
            self.store,
            {
                "graph_id": "graph-regression",
                "node_id": "node-1",
                "label": "Node 1",
                "type": EntityType.DEPARTMENT.value,
                "card_sections": [{"title": "Overview", "body": "Wrong", "icon": "", "order": 1}],
            },
        )

        self.assertEqual(result["code"], -32602)
        self.assertIn("body", result["message"])
        self.assertIn("content", result["message"])

    @unittest.skipUnless(os.environ.get("RUN_LIVE_LLM"), "manual live-LLM comprehension run")
    def test_live_llm_manual_stub(self) -> None:
        self.skipTest("Manual acceptance stub: run the fixed 5-op script against a live LLM client and require 5/5 x3.")
