from __future__ import annotations

import json
import unittest

from brain_ds.store.models import EdgeRow
from brain_ds.verify.edge_snapshot import (
    build_edge_snapshot,
    decode_cursor,
    enforce_large_graph_guard,
)


def _edge(
    edge_id: str, label: str, weight: float | None, evidence_ids: list[str] | None = None
) -> EdgeRow:
    return EdgeRow(
        graph_id="g",
        edge_id=edge_id,
        source="s",
        target="t",
        label=label,
        weight=weight,
        reasons=[],
        evidence_ids=evidence_ids,
        created_at="now",
    )


class EdgeSnapshotTests(unittest.TestCase):
    def test_sample_mode_is_bounded_and_returns_cursor(self) -> None:
        snapshot = build_edge_snapshot(
            graph_id="g",
            edges=[_edge("a", "rel", 0.1), _edge("b", "rel", 0.2), _edge("c", "rel", 0.3)],
            mode="sample",
            limit=2,
        )

        self.assertEqual([edge["edge_id"] for edge in snapshot["edges"]], ["a", "b"])
        self.assertEqual(snapshot["limit"], 2)
        self.assertIsNotNone(snapshot["next_cursor"])
        decoded = decode_cursor(str(snapshot["next_cursor"]))
        self.assertEqual(decoded["last_edge_id"], "b")

    def test_evidence_ranked_prioritizes_missing_evidence_then_low_weight(self) -> None:
        snapshot = build_edge_snapshot(
            graph_id="g",
            edges=[_edge("has", "rel", 0.9, ["e"]), _edge("missing", "rel", 0.1, [])],
            mode="evidence_ranked",
            limit=10,
        )

        self.assertEqual([edge["edge_id"] for edge in snapshot["edges"]], ["missing", "has"])

    def test_rejects_unbounded_limit_and_depth_above_three(self) -> None:
        with self.assertRaises(ValueError):
            build_edge_snapshot(graph_id="g", edges=[], mode="sample", limit=501)

        with self.assertRaises(ValueError):
            build_edge_snapshot(
                graph_id="g",
                edges=[],
                mode="sample",
                limit=50,
                neighborhood={"node_id": "s", "depth": 4, "direction": "both"},
            )

    def test_build_edge_snapshot_pure_layer_does_not_enforce_large_graph_guard(self) -> None:
        """The pure builder intentionally has no large-graph guard.

        ``build_edge_snapshot`` is the pure data-transformation layer: it receives
        an already-fetched edge list and knows nothing about total graph size.  The
        large-graph guard lives one layer up:

        * ``enforce_large_graph_guard`` (``brain_ds/verify/edge_snapshot.py``) is the
          pure guard function — tested by ``test_large_graph_guard_raises_*`` below.
        * The ``snapshot_edges`` MCP handler (``brain_ds/mcp/tools.py``) calls
          ``enforce_large_graph_guard`` (via ``store.get_graph_edge_count``) BEFORE
          invoking ``build_edge_snapshot``, so unbounded large-graph calls are
          rejected at the MCP boundary. Those handler-level rejection paths are
          exercised in ``tests/test_mcp_tools.py``.

        This test asserts the layer boundary: ``build_edge_snapshot`` itself must
        not raise when called directly on any edge list, regardless of conceptual
        graph size.  Removing this would silently couple the pure layer to the
        guard policy and break that separation.
        """
        edges = [_edge(f"e{i}", "rel", 0.5, ["ev"]) for i in range(5)]
        snapshot = build_edge_snapshot(
            graph_id="big-g",
            edges=edges,
            mode="sample",
            limit=None,  # resolves to DEFAULT_EDGE_SNAPSHOT_LIMIT=50
        )
        self.assertIsNotNone(snapshot)

    def test_large_graph_guard_raises_when_no_limit_no_mode_no_filter(self) -> None:
        """Task 5.3 RED: enforce_large_graph_guard raises ValueError for unbounded calls.

        For graphs >100k edges, a graph_id-only call with no explicit limit, no
        explicit mode, and no filter must raise ValueError('limit_required') so the
        MCP layer can map it to 400 limit_required.
        """
        with self.assertRaises(ValueError) as ctx:
            enforce_large_graph_guard(
                total_edge_count=100_001,
                has_explicit_limit=False,
                has_explicit_mode=False,
                has_filter=False,
            )
        self.assertIn("limit_required", str(ctx.exception))

    def test_large_graph_guard_does_not_raise_when_limit_provided(self) -> None:
        """Task 5.3/5.4: guard allows large graph call if explicit limit is given."""
        # Should not raise — caller provided an explicit limit.
        enforce_large_graph_guard(
            total_edge_count=200_000,
            has_explicit_limit=True,
            has_explicit_mode=False,
            has_filter=False,
        )

    def test_large_graph_guard_does_not_raise_when_mode_provided(self) -> None:
        """Task 5.3/5.4: guard allows large graph call if explicit mode is given."""
        enforce_large_graph_guard(
            total_edge_count=200_000,
            has_explicit_limit=False,
            has_explicit_mode=True,
            has_filter=False,
        )

    def test_large_graph_guard_does_not_raise_when_filter_provided(self) -> None:
        """Task 5.3/5.4: guard allows large graph call if a filter is given."""
        enforce_large_graph_guard(
            total_edge_count=200_000,
            has_explicit_limit=False,
            has_explicit_mode=False,
            has_filter=True,
        )

    def test_large_graph_guard_does_not_raise_for_small_graph(self) -> None:
        """Task 5.4: guard only applies to graphs >100k edges."""
        enforce_large_graph_guard(
            total_edge_count=100_000,  # exactly at the threshold — not over
            has_explicit_limit=False,
            has_explicit_mode=False,
            has_filter=False,
        )

    def test_payload_size_guard_raises_when_payload_exceeds_256kib(self) -> None:
        """Task 5.3 RED: payload cap — snapshot payload must not exceed 256 KiB.

        Construct a large edges list whose serialised JSON would exceed 256 KiB,
        then verify that enforce_payload_size_guard raises ValueError('payload_too_large').
        """
        from brain_ds.verify.edge_snapshot import enforce_payload_size_guard

        # Build a payload dict that clearly exceeds 256 KiB.
        # Each entry is ~620 bytes serialised; 500 entries → ~310 KiB > 256 KiB.
        large_payload = {"edges": [{"edge_id": "x" * 300, "data": "y" * 300} for _ in range(500)]}
        serialised = json.dumps(large_payload).encode("utf-8")
        self.assertGreater(len(serialised), 256 * 1024)

        with self.assertRaises(ValueError) as ctx:
            enforce_payload_size_guard(large_payload)
        self.assertIn("payload_too_large", str(ctx.exception))

    def test_payload_size_guard_allows_payload_within_256kib(self) -> None:
        """Task 5.4: small payload passes through the size guard unchanged."""
        from brain_ds.verify.edge_snapshot import enforce_payload_size_guard

        small_payload = {"edges": [{"edge_id": "a", "label": "owns"}]}
        # Should not raise.
        enforce_payload_size_guard(small_payload)

    def test_flags_missing_evidence_and_out_of_range_weight(self) -> None:
        snapshot = build_edge_snapshot(
            graph_id="g",
            edges=[
                _edge("missing", "rel", 0.6, []),
                _edge("heavy", "rel", 1.2, ["e1"]),
                _edge("ok", "rel", 0.8, ["e2"]),
            ],
            mode="sample",
            limit=10,
        )

        flags_by_edge = {edge["edge_id"]: edge["deterministic_flags"] for edge in snapshot["edges"]}
        self.assertEqual(
            flags_by_edge["missing"],
            [
                {
                    "code": "missing_evidence",
                    "dimension": "edge_evidence",
                    "severity": "SUGGESTION",
                    "message": "Edge has no cited evidence.",
                }
            ],
        )
        self.assertEqual(flags_by_edge["ok"], [])
        self.assertEqual(
            flags_by_edge["heavy"],
            [
                {
                    "code": "weight_out_of_range",
                    "dimension": "edge_weight",
                    "severity": "SUGGESTION",
                    "message": "Edge weight must be between 0 and 1.",
                }
            ],
        )
