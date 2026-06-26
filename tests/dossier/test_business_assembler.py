from __future__ import annotations

from types import SimpleNamespace
import unittest

from brain_ds.dossier.business_models import BusinessInterpretation
from brain_ds.dossier.models import DossierGapInputs, DossierGraphView


def node(
    node_id: str,
    label: str,
    node_type: str,
    supertype: str | None,
    parent_id: str | None = None,
    details: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=node_id,
        label=label,
        type=node_type,
        supertype=supertype,
        parent_id=parent_id,
        details=details or {"description": f"{label} business meaning"},
    )


def edge(source: str, target: str, label: str, confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(source=source, target=target, label=label, weight=confidence, edge_id=f"{source}->{target}:{label}")


def view(nodes: list[SimpleNamespace], edges: list[SimpleNamespace]) -> DossierGraphView:
    nodes_by_id = {item.id: item for item in nodes}
    adjacency: dict[str, set[str]] = {}
    children: dict[str | None, list[SimpleNamespace]] = {}
    for item in edges:
        adjacency.setdefault(item.source, set()).add(item.target)
        adjacency.setdefault(item.target, set()).add(item.source)
    for item in nodes:
        children.setdefault(item.parent_id, []).append(item)
    return DossierGraphView(nodes_by_id=nodes_by_id, adjacency=adjacency, children_by_parent=children, edges=edges)


class BusinessDossierAssemblerTests(unittest.TestCase):
    def test_business_sections_prioritize_entities_and_keep_sources_as_evidence(self) -> None:
        from brain_ds.dossier.business_assembler import assemble_business_dossier

        kpi = node("kpi-1", "On-time Delivery", "KPI", "metric")
        problem = node("problem-1", "Late Shipment Risk", "Problem / Improvement Area", "risk")
        department = node("dept-1", "Fulfillment", "Department", "actor")
        process = node("process-1", "Warehouse Dispatch", "Process", "process")
        actor = node("role-1", "Operations Owner", "Role", "actor")
        source = node("ds-1", "warehouse_db", "DataSource", "data")
        container = node("dc-1", "shipments", "DataContainer", "data-internal", parent_id="ds-1")

        dossier = assemble_business_dossier(
            view(
                [kpi, problem, department, process, actor, source, container],
                [
                    edge("kpi-1", "problem-1", "degraded-by"),
                    edge("kpi-1", "dept-1", "owned-by"),
                    edge("kpi-1", "process-1", "depends-on"),
                    edge("kpi-1", "role-1", "accountable"),
                    edge("kpi-1", "ds-1", "measured-by"),
                ],
            ),
            DossierGapInputs(),
            query="why are deliveries late?",
            interpretations=[BusinessInterpretation(id="kpi-1", label="On-time Delivery", entity_type="KPI", entity_ids=("kpi-1",), evidence_ids=("ds-1",), is_default=True)],
        )

        self.assertEqual([item["id"] for item in dossier.dossier["kpis"]], ["kpi-1"])
        self.assertEqual([item["id"] for item in dossier.dossier["problems"]], ["problem-1"])
        self.assertEqual([item["id"] for item in dossier.dossier["departments"]], ["dept-1"])
        self.assertEqual([item["id"] for item in dossier.dossier["processes"]], ["process-1"])
        self.assertEqual([item["id"] for item in dossier.dossier["actors"]], ["role-1"])
        self.assertEqual([item["id"] for item in dossier.evidence_sources], ["ds-1", "dc-1"])
        self.assertNotIn("ds-1", {item["id"] for section in dossier.dossier.values() for item in section})
        self.assertFalse(dossier.uncertainty.source_heavy)
        self.assertFalse(dossier.uncertainty.business_light)

    def test_source_only_evidence_surfaces_business_light_uncertainty(self) -> None:
        from brain_ds.dossier.business_assembler import assemble_business_dossier

        source = node("ds-1", "raw_margin_export", "DataSource", "data")

        dossier = assemble_business_dossier(
            view([source], []),
            DossierGapInputs(),
            query="margin risk",
            interpretations=[BusinessInterpretation(id="ds-1", label="raw_margin_export", entity_type="DataSource", entity_ids=("ds-1",), evidence_ids=("ds-1",), is_default=True)],
        )

        self.assertTrue(dossier.uncertainty.source_heavy)
        self.assertTrue(dossier.uncertainty.business_light)
        self.assertEqual(dossier.evidence_sources[0]["id"], "ds-1")
        self.assertEqual(dossier.dossier["kpis"], [])
        self.assertEqual(dossier.dossier["problems"], [])

    def test_uncertainty_and_pending_question_proposals_are_visible_read_path_data(self) -> None:
        from brain_ds.dossier.business_assembler import assemble_business_dossier

        kpi = node("kpi-1", "Revenue", "KPI", "metric")
        weak = {"from_node": "kpi-1", "to_node": "dept-1", "relationship": "owned-by", "confidence": 0.21}
        unconfirmed = {"candidate_id": "edge-7", "from_node": "kpi-1", "to_node": "dept-1", "relationship": "owned-by", "source": "confidence_ledger"}

        dossier = assemble_business_dossier(
            view([kpi], []),
            DossierGapInputs(
                completeness=[{"gap_type": "missing_owner", "target_node_id": "kpi-1"}],
                currency=[{"target_node_id": "kpi-1", "criticality": "high", "description": "Revenue mapping is stale"}],
                weak_edges=[weak],
                unconfirmed_lineage=[unconfirmed],
            ),
            query="revenue owner",
            interpretations=[BusinessInterpretation(id="kpi-1", label="Revenue", entity_type="KPI", entity_ids=("kpi-1",), is_default=True)],
        )

        self.assertEqual(dossier.uncertainty.completeness, [{"gap_type": "missing_owner", "target_node_id": "kpi-1"}])
        self.assertEqual(dossier.uncertainty.currency[0]["description"], "Revenue mapping is stale")
        self.assertEqual(dossier.uncertainty.weak_edges, [weak])
        self.assertEqual(len(dossier.pending_question_proposals), 1)
        proposal = dossier.pending_question_proposals[0]
        self.assertEqual(proposal.target_node_id, "dept-1")
        self.assertEqual(proposal.gap_kind, "owned-by")
        self.assertIn("Revenue", proposal.question_text)


if __name__ == "__main__":
    unittest.main()
