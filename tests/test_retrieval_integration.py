"""Integration tests for the retrieve_context handler (PR3 Brick D, Phase 3).

Covers:
  - R-11 scope-out: retrieve_context must issue ZERO write SQL statements
  - R-11 scope-out: serialized_for_llm must never contain the word "invalidated"
  - Full chain: serialized_for_llm is always a non-empty string (not "")
  - serialized_for_llm is always bounded (≤ 256 KiB)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brain_ds.store.graph_store import GraphStore

MAX_BYTES = 256 * 1024  # 256 KiB


def _make_store(temp_dir: str) -> tuple[GraphStore, str]:
    """Create a GraphStore with a graph, nodes, and edges seeded for retrieval tests."""
    db_path = Path(temp_dir) / ".brain_ds" / "store.db"
    db_path.parent.mkdir(parents=True)
    store = GraphStore(str(db_path))
    graph_id = "g-integration"
    store.meta_repo.save_graph_meta(
        graph_id=graph_id,
        workspace_root=temp_dir,
        workspace_path=temp_dir,
        project="p-int",
        org="o-int",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    store.upsert_node(graph_id, {"id": "N1", "label": "Process Alpha", "type": "Task", "supertype": "Work"})
    store.upsert_node(graph_id, {"id": "N2", "label": "Process Beta", "type": "Process", "supertype": "Business"})
    store.upsert_node(graph_id, {"id": "N3", "label": "Process Gamma", "type": "Role", "supertype": "Work"})
    store.upsert_edge(graph_id, {"source": "N1", "target": "N2", "label": "feeds", "weight": 0.8, "evidence_ids": []})
    store.upsert_edge(graph_id, {"source": "N2", "target": "N3", "label": "triggers", "weight": 0.6, "evidence_ids": []})
    return store, graph_id


class ScopeOutZeroWriteSqlTests(unittest.TestCase):
    """R-11: retrieve_context must not execute any INSERT/UPDATE/DELETE SQL."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store, self.graph_id = _make_store(self.temp_dir.name)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_retrieve_context_issues_zero_write_sql(self) -> None:
        """R-11: no INSERT/UPDATE/DELETE/CREATE/DROP/ALTER SQL is executed during retrieve_context."""
        write_statements: list[str] = []
        _WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE")

        def _trace(sql: str) -> None:
            upper = sql.strip().upper()
            if any(upper.startswith(prefix) for prefix in _WRITE_PREFIXES):
                write_statements.append(sql)

        self.store.conn.set_trace_callback(_trace)
        try:
            result = self._call({"graph_id": self.graph_id, "query": "Alpha"})
        finally:
            self.store.conn.set_trace_callback(None)

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        self.assertEqual(
            write_statements,
            [],
            f"Expected zero write SQL; found {len(write_statements)} statement(s):\n"
            + "\n".join(write_statements[:5]),
        )

    def test_retrieve_context_zero_writes_with_depth_two(self) -> None:
        """R-11: depth=2 call also issues no write SQL."""
        write_statements: list[str] = []
        _WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE")

        def _trace(sql: str) -> None:
            upper = sql.strip().upper()
            if any(upper.startswith(prefix) for prefix in _WRITE_PREFIXES):
                write_statements.append(sql)

        self.store.conn.set_trace_callback(_trace)
        try:
            result = self._call({"graph_id": self.graph_id, "query": "Process", "depth": 2})
        finally:
            self.store.conn.set_trace_callback(None)

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        self.assertEqual(write_statements, [], "depth=2 retrieve_context must also issue zero write SQL")


class ScopeOutNoInvalidatedInSerializedTests(unittest.TestCase):
    """R-11: serialized_for_llm must not contain any invalidated edge data."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store, self.graph_id = _make_store(self.temp_dir.name)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def _seed_invalidated_edge(self) -> None:
        """Add an edge then push an 'invalidated' ledger row for it."""
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N1", "target": "N3", "label": "invalidated_link", "weight": 0.99, "evidence_ids": []},
        )
        # Find the newly created edge_id and mark it invalidated via the ledger
        edges = self.store.query_edges(self.graph_id)
        inv_edge = next((e for e in edges if e.label == "invalidated_link"), None)
        if inv_edge is not None:
            self.store.append_ledger(
                self.graph_id,
                target_id=inv_edge.edge_id,
                target_type="edge",
                status="invalidated",
                provenance="generated",
                captured_at="2026-01-01T00:00:00+00:00",
            )

    def test_serialized_for_llm_contains_no_invalidated_substring(self) -> None:
        """R-11: even with invalidated edges in the store, they must not appear in the LLM output."""
        self._seed_invalidated_edge()
        result = self._call({"graph_id": self.graph_id, "query": "Process"})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        serialized = result.get("serialized_for_llm", "")
        self.assertNotIn(
            "invalidated",
            serialized.lower(),
            "R-11: 'invalidated' must never appear in serialized_for_llm",
        )


class SerializedForLlmPresenceAndBoundTests(unittest.TestCase):
    """serialized_for_llm is always present, non-empty, and bounded (R-03, R-07, R-08)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store, self.graph_id = _make_store(self.temp_dir.name)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_serialized_for_llm_is_non_empty_string(self) -> None:
        """PR3 wires the serializer: serialized_for_llm must no longer be an empty string."""
        result = self._call({"graph_id": self.graph_id, "query": "Alpha"})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        serialized = result.get("serialized_for_llm", "")
        self.assertIsInstance(serialized, str)
        self.assertGreater(
            len(serialized),
            0,
            "PR3: serialized_for_llm must be a non-empty string (not the placeholder '')",
        )

    def test_serialized_for_llm_present_on_depth_two_call(self) -> None:
        """serialized_for_llm is always present and bounded on depth=2 calls."""
        result = self._call({"graph_id": self.graph_id, "query": "Process", "depth": 2})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        self.assertIn("serialized_for_llm", result)
        serialized = result["serialized_for_llm"]
        byte_length = len(serialized.encode("utf-8"))
        self.assertLessEqual(
            byte_length,
            MAX_BYTES + 200,  # 200 bytes margin for sentinel
            f"serialized_for_llm exceeds 256 KiB: {byte_length} bytes",
        )

    def test_serialized_for_llm_contains_anchor_label(self) -> None:
        """serialized_for_llm contains the anchor node label in the ANCHOR header."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        serialized = result.get("serialized_for_llm", "")
        self.assertIn("[ANCHOR:", serialized, "serialized_for_llm must include an [ANCHOR:] header")
        self.assertIn("Process Alpha", serialized, "The anchor node label must appear in the output")

    def test_serialized_for_llm_hierarchy_and_connections_present(self) -> None:
        """serialized_for_llm always has both a HIERARCHY: and a CONNECTIONS section."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        serialized = result.get("serialized_for_llm", "")
        self.assertIn("HIERARCHY:", serialized)
        self.assertIn("CONNECTIONS", serialized)

    def test_clusterless_retrieval_keeps_existing_bfs_contract(self) -> None:
        """Cluster routing is additive: graphs without cluster metadata still use BFS anchors."""
        result = self._call({"graph_id": self.graph_id, "query": "Alpha", "limit": 3})

        self.assertNotIn("code", result, f"retrieve_context returned an error: {result}")
        self.assertEqual(result["module_route"], {"mode": "bfs", "clusters": []})
        self.assertEqual([anchor["id"] for anchor in result["anchors"]], ["N1"])
        self.assertIn("Process Alpha", result.get("serialized_for_llm", ""))

    def test_serialized_for_llm_global_cap_includes_large_module_route_summaries(self) -> None:
        """The 256 KiB cap applies even when cluster route summaries dominate the payload."""
        from brain_ds.retrieval.serialization import _TRUNCATION_SENTINEL, serialize_for_llm

        serialized = serialize_for_llm(
            [],
            [],
            {},
            module_route={
                "mode": "cluster",
                "clusters": [
                    {
                        "id": "CL_HUGE",
                        "name": "Huge Route",
                        "status": "confirmed",
                        "summary": "route summary " * 30_000,
                        "routing_weight": 1.0,
                    }
                ],
            },
        )

        self.assertLessEqual(len(serialized.encode("utf-8")), MAX_BYTES)
        self.assertTrue(serialized.endswith(_TRUNCATION_SENTINEL))


if __name__ == "__main__":
    unittest.main()
