from __future__ import annotations

from types import SimpleNamespace
import unittest

from brain_ds.dossier.models import DossierGapInputs, DossierGraphView
from brain_ds.retrieval.models import RetrievalCandidate
from brain_ds.scoring.retrieval import SignalScores


def node(node_id: str, label: str, node_type: str, supertype: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=node_id, label=label, type=node_type, supertype=supertype, parent_id=None, details={"description": f"{label} business meaning"})


def edge(source: str, target: str, label: str) -> SimpleNamespace:
    return SimpleNamespace(source=source, target=target, label=label, weight=0.9, edge_id=f"{source}->{target}:{label}")


def view(nodes: list[SimpleNamespace], edges: list[SimpleNamespace]) -> DossierGraphView:
    adjacency: dict[str, set[str]] = {}
    for item in edges:
        adjacency.setdefault(item.source, set()).add(item.target)
        adjacency.setdefault(item.target, set()).add(item.source)
    return DossierGraphView(nodes_by_id={item.id: item for item in nodes}, adjacency=adjacency, edges=edges)


class BusinessReadPathTests(unittest.TestCase):
    def test_build_business_dossier_payload_composes_router_assembler_and_serializer_without_writes(self) -> None:
        from brain_ds.dossier.business_read_path import build_business_dossier_payload

        kpi = node("kpi-1", "On-time Delivery", "KPI", "metric")
        source = node("ds-1", "warehouse_db", "DataSource", "data")

        payload = build_business_dossier_payload(
            graph_view=view([kpi, source], [edge("kpi-1", "ds-1", "measured-by")]),
            gaps=DossierGapInputs(currency=[{"description": "Warehouse data is stale"}]),
            query="delivery performance",
            candidates=[
                RetrievalCandidate(
                    id="kpi-1",
                    label="On-time Delivery",
                    signals=SignalScores(lexical=0.9, semantic=0.8, governance=0.8, graph=0.6),
                    metadata={"type": "KPI", "evidence_ids": ["ds-1"]},
                )
            ],
            max_alternatives=3,
        )

        self.assertEqual(payload["selected_interpretation_id"], "kpi-1")
        self.assertEqual(payload["dossier"]["kpis"][0]["id"], "kpi-1")
        self.assertEqual(payload["evidence_sources"][0]["id"], "ds-1")
        self.assertEqual(payload["uncertainty"]["currency"][0]["description"], "Warehouse data is stale")
        self.assertEqual(payload["pending_questions_created"], [])


if __name__ == "__main__":
    unittest.main()
