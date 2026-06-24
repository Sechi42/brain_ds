"""Tests for pending-confirmation exposure in build_render_context (Phase 5.1 / 5.2).

These tests cover:
- pending_confirmations key is present when a store is supplied
- count matches the number of pending rows for the graph
- list contains dicts with expected fields
- no-store path: key absent (backwards compat) OR present with empty list
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brain_ds.ontology import Graph
from brain_ds.store.graph_store import GraphStore
from brain_ds.ui.render_context import build_render_context


def _minimal_graph_payload() -> dict:
    return {
        "org": "TestOrg",
        "generated_at": "2026-01-01T00:00:00Z",
        "nodes": [{"id": "n1", "label": "Node1", "type": "Department"}],
        "edges": [],
    }


def _make_store_with_pending(tmp_dir: Path, graph_id: str) -> GraphStore:
    """Create a GraphStore with two pending-confirmation ledger rows for *graph_id*."""
    store = GraphStore(str(tmp_dir / "store.db"))
    store.create_graph(graph_id, name="TestOrg")

    ledger = store.ledger_repo
    ledger.append(
        graph_id,
        target_type="node",
        target_id="n1",
        status="needs-confirmation",
        initial_confidence=0.5,
        current_confidence=0.5,
        fact_label="Role",
        fact_subject_type="Person",
        provenance="generated",
        captured_at="2026-01-01T00:00:00Z",
    )
    ledger.append(
        graph_id,
        target_type="node",
        target_id="n2",
        status="needs-confirmation",
        initial_confidence=0.3,
        current_confidence=0.3,
        fact_label="Department",
        fact_subject_type="Role",
        provenance="generated",
        captured_at="2026-01-01T00:00:00Z",
    )
    return store


class TestRenderContextPendingConfirmationsWithStore(unittest.TestCase):
    """When a store is supplied, pending_confirmations must appear in output."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.graph_id = "g-pending-test"
        self.store = _make_store_with_pending(self.tmp_dir, self.graph_id)
        self.graph = Graph.from_v1(_minimal_graph_payload())

    def tearDown(self):
        # Close the store's SQLite connection before removing the temp directory
        # to avoid Windows "file in use" errors on cleanup.
        try:
            self.store.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_pending_confirmations_key_present_when_store_supplied(self):
        ctx = build_render_context(self.graph, graph_id=self.graph_id, store=self.store)
        self.assertIn("pending_confirmations", ctx)

    def test_pending_confirmations_count_matches_rows(self):
        ctx = build_render_context(self.graph, graph_id=self.graph_id, store=self.store)
        self.assertEqual(ctx["pending_confirmations"]["count"], 2)

    def test_pending_confirmations_list_length_matches_count(self):
        ctx = build_render_context(self.graph, graph_id=self.graph_id, store=self.store)
        pending = ctx["pending_confirmations"]
        self.assertEqual(len(pending["items"]), pending["count"])

    def test_pending_confirmation_items_have_expected_fields(self):
        ctx = build_render_context(self.graph, graph_id=self.graph_id, store=self.store)
        for item in ctx["pending_confirmations"]["items"]:
            self.assertIn("target_id", item)
            self.assertIn("target_type", item)
            self.assertIn("status", item)
            self.assertIn("fact_label", item)

    def test_pending_confirmation_status_is_needs_confirmation(self):
        ctx = build_render_context(self.graph, graph_id=self.graph_id, store=self.store)
        for item in ctx["pending_confirmations"]["items"]:
            self.assertEqual(item["status"], "needs-confirmation")

    def test_pending_confirmations_empty_when_none_pending(self):
        """Graph with no pending rows should return count=0 and empty items."""
        store2 = GraphStore(str(self.tmp_dir / "store2.db"))
        try:
            store2.create_graph("g-empty", name="TestOrg")
            ctx = build_render_context(self.graph, graph_id="g-empty", store=store2)
            self.assertEqual(ctx["pending_confirmations"]["count"], 0)
            self.assertEqual(ctx["pending_confirmations"]["items"], [])
        finally:
            try:
                store2.conn.close()
            except Exception:
                pass


class TestRenderContextPendingConfirmationsNoStore(unittest.TestCase):
    """When no store is supplied, existing callers must not break."""

    def test_no_store_no_graph_id_does_not_crash(self):
        """Existing callers pass no store — they must continue to work."""
        graph = Graph.from_v1(_minimal_graph_payload())
        ctx = build_render_context(graph)
        # pending_confirmations should be absent (backwards compat) or empty
        if "pending_confirmations" in ctx:
            self.assertEqual(ctx["pending_confirmations"]["count"], 0)
            self.assertEqual(ctx["pending_confirmations"]["items"], [])

    def test_store_supplied_but_no_graph_id_does_not_crash(self):
        """If store is given but graph_id is None, must not raise."""
        tmp = tempfile.TemporaryDirectory()
        store = None
        try:
            store = GraphStore(str(Path(tmp.name) / "s.db"))
            graph = Graph.from_v1(_minimal_graph_payload())
            ctx = build_render_context(graph, store=store)
            # Should return 0 pending (no graph to query)
            if "pending_confirmations" in ctx:
                self.assertEqual(ctx["pending_confirmations"]["count"], 0)
        finally:
            if store is not None:
                try:
                    store.conn.close()
                except Exception:
                    pass
            tmp.cleanup()
