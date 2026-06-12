from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from brain_ds.mcp.tools import list_nodes, search_graph
from brain_ds.store.graph_store import GraphStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_SKILL_PATHS = [
    PROJECT_ROOT / "skills" / "map-connections" / "SKILL.md",
    PROJECT_ROOT / ".opencode" / "skills" / "map-connections" / "SKILL.md",
]
BRD_SKILL_PATHS = [
    PROJECT_ROOT / "skills" / "generate-brd" / "SKILL.md",
    PROJECT_ROOT / ".opencode" / "skills" / "generate-brd" / "SKILL.md",
]


class TestMapGenerateSkillContracts(unittest.TestCase):
    def test_map_connections_skill_mentions_sqlite_retrieval_and_mcp_persistence(self) -> None:
        required_markers = [
            "Run typed SQLite retrievals against the resolved org graph.",
            '"tool": "list_nodes"',
            '"tool": "search_graph"',
            '"tool": "update_node"',
            '"tool": "add_edge"',
            "typed SQL filters are not equivalent to Engram substring search",
            "validate the difference on a seeded vault before assuming parity",
        ]
        forbidden_markers = [
            "Run these **12 queries in parallel**:",
            "For **every** unique ID, call `mem_get_observation(id)`.",
        ]
        for path in MAP_SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)
            for marker in forbidden_markers:
                with self.subTest(path=path.name, forbidden=marker):
                    self.assertNotIn(marker, content)

    def test_generate_brd_skill_mentions_sqlite_retrieval(self) -> None:
        required_markers = [
            "Run typed SQLite retrievals against the resolved org graph.",
            '"tool": "list_nodes"',
            '"tool": "search_graph"',
            "typed SQL filters are not equivalent to Engram substring search",
            "validate the difference on a seeded vault before assuming parity",
        ]
        forbidden_markers = [
            "Run these **11 queries in parallel**:",
            "Call `mem_get_observation(id)` for every ID.",
        ]
        for path in BRD_SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)
            for marker in forbidden_markers:
                with self.subTest(path=path.name, forbidden=marker):
                    self.assertNotIn(marker, content)


class TestSqliteRetrievalSemantics(unittest.TestCase):
    def test_typed_list_nodes_is_not_equivalent_to_substring_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GraphStore(str(Path(tmp_dir) / "store.db"))
            try:
                graph_id = store.create_graph("logitrans")
                store.upsert_node(
                    graph_id,
                    {
                        "id": "ds-erp",
                        "label": "ERP Feed",
                        "type": "Data Source",
                        "supertype": "Source",
                        "details": {"where": "ERP system", "why": "Orders"},
                    },
                )
                store.upsert_node(
                    graph_id,
                    {
                        "id": "ds-eta",
                        "label": "ETA Feed",
                        "type": "Data Source",
                        "supertype": "Source",
                        "details": {"where": "Telematics", "why": "ETA updates"},
                    },
                )
                store.upsert_node(
                    graph_id,
                    {
                        "id": "role-ops",
                        "label": "Operations Lead",
                        "type": "Role",
                        "supertype": "People",
                        "details": {"where": "Control room", "why": "Reviews ETA feed daily"},
                    },
                )

                typed_results = list_nodes(store, {"graph_id": graph_id, "type": "Data Source"})
                substring_results = search_graph(store, {"graph_id": graph_id, "query": "ETA"})

                self.assertEqual([item["id"] for item in cast(list[dict[str, Any]], typed_results)], ["ds-erp", "ds-eta"])
                self.assertEqual(
                    [item["id"] for item in cast(list[dict[str, Any]], substring_results)],
                    ["ds-eta", "role-ops"],
                )
            finally:
                store.close()
