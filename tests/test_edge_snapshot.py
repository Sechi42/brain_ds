from __future__ import annotations

import unittest

from brain_ds.store.models import EdgeRow
from brain_ds.verify.edge_snapshot import build_edge_snapshot, decode_cursor


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
