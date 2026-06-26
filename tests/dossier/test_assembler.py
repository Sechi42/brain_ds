from __future__ import annotations

from types import SimpleNamespace
import unittest

from brain_ds.dossier.models import DossierGapInputs, DossierGraphView
from brain_ds.ontology.relationship_types import RelationshipType


def node(node_id: str, label: str, node_type: str, supertype: str | None, parent_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=node_id,
        label=label,
        type=node_type,
        supertype=supertype,
        parent_id=parent_id,
        details={"description": f"{label} business meaning"},
    )


def edge(source: str, target: str, label: str, confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(source=source, target=target, label=label, weight=confidence, edge_id=f"{source}->{target}:{label}")


class AssembleKpiDossierTests(unittest.TestCase):
    def _view(
        self,
        nodes: list[SimpleNamespace],
        edges: list[SimpleNamespace],
        ledger_status_by_target: dict[str, str] | None = None,
    ) -> DossierGraphView:
        nodes_by_id = {item.id: item for item in nodes}
        adjacency: dict[str, set[str]] = {}
        for item in edges:
            adjacency.setdefault(item.source, set()).add(item.target)
            adjacency.setdefault(item.target, set()).add(item.source)
        children: dict[str | None, list[SimpleNamespace]] = {}
        for item in nodes:
            children.setdefault(item.parent_id, []).append(item)
        return DossierGraphView(
            nodes_by_id=nodes_by_id,
            adjacency=adjacency,
            children_by_parent=children,
            edges=edges,
            ledger_status_by_target=ledger_status_by_target or {},
        )

    def test_reaches_data_source_actor_and_process_from_kpi(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "On-time Delivery", "KPI", "metric")
        ds = node("ds", "Warehouse DB", "DataSource", "data")
        role = node("role", "Ops Manager", "Role", "actor")
        heuristic = node("heuristic", "Late-order Rule", "Heuristic", "process")
        problem = node("problem", "Delay Risk", "Risk", "risk")
        dossier = assemble_kpi_dossier(
            self._view(
                [kpi, ds, role, heuristic, problem],
                [
                    edge("kpi", "ds", RelationshipType.MEASURED_BY.value),
                    edge("kpi", "role", RelationshipType.ACCOUNTABLE.value),
                    edge("kpi", "heuristic", RelationshipType.DEPENDS_ON.value),
                    edge("kpi", "problem", RelationshipType.DEGRADED_BY.value),
                ],
            ),
            DossierGapInputs(),
            kpi_node_id="kpi",
            depth=2,
        )

        self.assertEqual([facet.node.id for facet in dossier.data_sources], ["ds"])
        self.assertEqual([facet.node.id for facet in dossier.actors], ["role"])
        self.assertEqual([facet.node.id for facet in dossier.processes], ["heuristic"])

    def test_processes_exclude_standalone_process_type(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Revenue", "KPI", "metric")
        process = node("process", "Legacy Process", "Process", "process")
        project = node("project", "Margin Program", "Project", "process")
        dossier = assemble_kpi_dossier(
            self._view([kpi, process, project], [edge("kpi", "process", "depends-on"), edge("kpi", "project", "depends-on")]),
            DossierGapInputs(),
            kpi_node_id="kpi",
        )

        self.assertEqual([facet.node.id for facet in dossier.processes], ["project"])

    def test_hierarchy_inferred_container_stays_out_of_first_class_content(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Inventory Accuracy", "KPI", "metric")
        ds = node("ds", "ERP", "DataSource", "data")
        table = node("dc", "inventory_snapshot", "DataContainer", "data-internal", parent_id="ds")
        dossier = assemble_kpi_dossier(
            self._view([kpi, ds, table], [edge("kpi", "ds", "measured-by")]),
            DossierGapInputs(),
            kpi_node_id="kpi",
        )

        surfaced_container_ids = [container.node.id for source in dossier.data_sources for container in source.containers]
        self.assertEqual(surfaced_container_ids, [])
        self.assertEqual(dossier.limitations.unconfirmed_lineage[0]["to_node"], "dc")
        self.assertEqual(dossier.limitations.unconfirmed_lineage[0]["source"], "hierarchy-inferred")

    def test_pending_lineage_input_stays_in_limitations_only(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Inventory Accuracy", "KPI", "metric")
        ds = node("ds", "ERP", "DataSource", "data")
        table = node("dc", "inventory_snapshot", "DataContainer", "data-internal", parent_id="ds")
        dossier = assemble_kpi_dossier(
            self._view([kpi, ds, table], [edge("kpi", "ds", "measured-by")]),
            DossierGapInputs(
                unconfirmed_lineage=[
                    {
                        "candidate_id": "ledger-7",
                        "from_node": "kpi",
                        "to_node": "dc",
                        "relationship": "measured-from",
                        "source": "insert_pending_question",
                    }
                ]
            ),
            kpi_node_id="kpi",
        )

        surfaced_container_ids = [container.node.id for source in dossier.data_sources for container in source.containers]
        self.assertEqual(surfaced_container_ids, [])
        self.assertIn(
            {
                "candidate_id": "ledger-7",
                "from_node": "kpi",
                "to_node": "dc",
                "relationship": "measured-from",
                "source": "insert_pending_question",
            },
            dossier.limitations.unconfirmed_lineage,
        )

    def test_confirmed_measured_from_container_and_field_are_first_class(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Churn", "KPI", "metric")
        ds = node("ds", "CRM", "DataSource", "data")
        table = node("dc", "customers", "DataContainer", "data-internal", parent_id="ds")
        field = node("field", "cancelled_at", "DataField", "data-internal", parent_id="dc")
        container_edge = edge("kpi", "dc", "measured-from")
        field_edge = edge("kpi", "field", "measured-from")
        dossier = assemble_kpi_dossier(
            self._view(
                [kpi, ds, table, field],
                [container_edge, field_edge],
                {container_edge.edge_id: "confirmed", field_edge.edge_id: "confirmed"},
            ),
            DossierGapInputs(),
            kpi_node_id="kpi",
        )

        source = dossier.data_sources[0]
        self.assertEqual(source.node.id, "ds")
        self.assertEqual(source.containers[0].lineage_source, "confirmed-edge")
        self.assertEqual([item.id for item in source.containers[0].fields], ["field"])
        self.assertEqual(dossier.limitations.unconfirmed_lineage, [])

    def test_unconfirmed_measured_from_container_edge_stays_in_limitations_only(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Churn", "KPI", "metric")
        ds = node("ds", "CRM", "DataSource", "data")
        table = node("dc", "customers", "DataContainer", "data-internal", parent_id="ds")
        unconfirmed_edge = edge("kpi", "dc", RelationshipType.MEASURED_FROM.value)

        dossier = assemble_kpi_dossier(
            self._view([kpi, ds, table], [unconfirmed_edge], {unconfirmed_edge.edge_id: "needs-confirmation"}),
            DossierGapInputs(),
            kpi_node_id="kpi",
        )

        surfaced_container_ids = [container.node.id for source in dossier.data_sources for container in source.containers]
        self.assertEqual(surfaced_container_ids, [])
        self.assertIn(
            {
                "candidate_id": unconfirmed_edge.edge_id,
                "from_node": "kpi",
                "to_node": "dc",
                "relationship": RelationshipType.MEASURED_FROM.value,
                "source": "confidence_ledger",
            },
            dossier.limitations.unconfirmed_lineage,
        )

    def test_unconfirmed_measured_from_field_edge_stays_in_limitations_only(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Churn", "KPI", "metric")
        ds = node("ds", "CRM", "DataSource", "data")
        table = node("dc", "customers", "DataContainer", "data-internal", parent_id="ds")
        field = node("field", "cancelled_at", "DataField", "data-internal", parent_id="dc")
        confirmed_container = edge("kpi", "dc", RelationshipType.MEASURED_FROM.value)
        unconfirmed_field = edge("kpi", "field", RelationshipType.MEASURED_FROM.value)

        dossier = assemble_kpi_dossier(
            self._view(
                [kpi, ds, table, field],
                [confirmed_container, unconfirmed_field],
                {confirmed_container.edge_id: "confirmed", unconfirmed_field.edge_id: "needs-confirmation"},
            ),
            DossierGapInputs(),
            kpi_node_id="kpi",
        )

        self.assertEqual(dossier.data_sources[0].containers[0].fields, [])
        self.assertIn(
            {
                "candidate_id": unconfirmed_field.edge_id,
                "from_node": "kpi",
                "to_node": "field",
                "relationship": RelationshipType.MEASURED_FROM.value,
                "source": "confidence_ledger",
            },
            dossier.limitations.unconfirmed_lineage,
        )

    def test_no_connections_surfaces_structural_limitations(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        dossier = assemble_kpi_dossier(
            self._view([node("kpi", "Quality", "KPI", "metric")], []),
            DossierGapInputs(completeness=[{"gap_type": "missing_data_source"}], currency=[{"description": "stale"}], weak_edges=[{"from_node": "kpi"}]),
            kpi_node_id="kpi",
        )

        self.assertEqual(dossier.data_sources, [])
        self.assertTrue(dossier.limitations.unmapped_sources)
        self.assertTrue(dossier.limitations.missing_ownership)
        self.assertTrue(dossier.limitations.missing_process)
        self.assertEqual(dossier.limitations.completeness, [{"gap_type": "missing_data_source"}])
        self.assertEqual(dossier.limitations.currency, [{"description": "stale"}])
        self.assertEqual(dossier.limitations.weak_edges, [{"from_node": "kpi"}])

    def test_depth_boundary_cycles_and_deduplicated_gap_inputs(self) -> None:
        from brain_ds.dossier.assembler import assemble_kpi_dossier

        kpi = node("kpi", "Cost", "KPI", "metric")
        ds = node("ds", "Finance Lake", "DataSource", "data")
        far = node("far", "Hop Three Role", "Role", "actor")
        repeated_gap = {"description": "same gap"}
        dossier = assemble_kpi_dossier(
            self._view([kpi, ds, far], [edge("kpi", "ds", "measured-by"), edge("ds", "kpi", "uses"), edge("ds", "far", "uses")]),
            DossierGapInputs(completeness=[repeated_gap, repeated_gap], currency=[repeated_gap, repeated_gap], weak_edges=[repeated_gap, repeated_gap]),
            kpi_node_id="kpi",
            depth=1,
        )

        self.assertEqual(dossier.actors, [])
        self.assertEqual(dossier.limitations.completeness, [repeated_gap])
        self.assertEqual(dossier.limitations.currency, [repeated_gap])
        self.assertEqual(dossier.limitations.weak_edges, [repeated_gap])


if __name__ == "__main__":
    unittest.main()
