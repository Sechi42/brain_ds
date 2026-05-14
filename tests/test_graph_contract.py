import unittest

from brain_ds.ontology import CardSection, Edge, EntityType, EvidenceRecord, Graph, Node


class TestSupportingDataclasses(unittest.TestCase):
    def test_evidence_record_defaults_and_fields(self):
        record = EvidenceRecord(
            id="obs-1",
            type="observation",
            source="engram",
            content="Some evidence",
        )
        self.assertIsNone(record.provenance)
        self.assertEqual(record.timestamp, "")

        full = EvidenceRecord(
            id="obs-2",
            type="observation",
            source="engram",
            content="Other evidence",
            provenance={"session_id": "s1"},
            timestamp="2026-05-13T23:00:00Z",
        )
        self.assertEqual(full.provenance, {"session_id": "s1"})
        self.assertEqual(full.timestamp, "2026-05-13T23:00:00Z")

    def test_card_section_defaults_and_fields(self):
        section = CardSection(title="Summary", content="hello")
        self.assertEqual(section.icon, "")
        self.assertEqual(section.order, 0)

        full = CardSection(title="Signals", content="text", icon="sparkles", order=2)
        self.assertEqual(full.icon, "sparkles")
        self.assertEqual(full.order, 2)


class TestGraphContract(unittest.TestCase):
    def test_graph_defaults(self):
        graph = Graph()
        self.assertEqual(graph.schema_version, "2.0.0")
        self.assertEqual(graph.org, "")
        self.assertEqual(graph.generated_at, "")
        self.assertEqual(graph.nodes, [])
        self.assertEqual(graph.edges, [])
        self.assertEqual(graph.evidence, [])

    def test_node_optional_fields_default_to_none(self):
        node = Node(id="n1", label="Sales", type=EntityType.DEPARTMENT)
        self.assertIsNone(node.supertype)
        self.assertIsNone(node.card_sections)
        self.assertIsNone(node.evidence_ids)
        self.assertIsNone(node.editable_fields)
        self.assertIsNone(node.layout_hint)

    def test_from_v1_upgrades_shape(self):
        v1 = {
            "nodes": [{"id": "n1", "label": "Sales", "type": "Department", "details": {}}],
            "edges": [{"source": "n1", "target": "n2", "label": "depends-on"}],
        }

        graph = Graph.from_v1(v1)

        self.assertEqual(graph.schema_version, "2.0.0")
        self.assertEqual(graph.org, "")
        self.assertEqual(graph.generated_at, "")
        self.assertEqual(graph.evidence, [])
        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(len(graph.edges), 1)
        self.assertIsNone(graph.nodes[0].evidence_ids)

    def test_to_dict_roundtrip_preserves_v2_fields_and_derives_supertype(self):
        graph = Graph(
            org="Acme",
            generated_at="2026-05-13T23:00:00Z",
            nodes=[
                Node(
                    id="n1",
                    label="Sales",
                    type=EntityType.DEPARTMENT,
                    card_sections=[CardSection(title="Summary", content="Team", icon="briefcase", order=1)],
                    evidence_ids=["obs-1"],
                    editable_fields=["label", "details"],
                    layout_hint={"x": 10, "y": 20},
                )
            ],
            edges=[
                Edge(
                    source="n1",
                    target="n2",
                    label="depends-on",
                    edge_id="edge-1",
                    weight=0.7,
                    reasons=["scored"],
                    evidence_ids=["obs-1"],
                )
            ],
            evidence=[
                EvidenceRecord(
                    id="obs-1",
                    type="observation",
                    source="engram",
                    content="Sales relies on target",
                    provenance={"session_id": "s1"},
                    timestamp="2026-05-13T23:00:00Z",
                )
            ],
        )

        payload = graph.to_dict()
        self.assertEqual(payload["schema_version"], "2.0.0")
        self.assertEqual(payload["org"], "Acme")
        self.assertEqual(payload["generated_at"], "2026-05-13T23:00:00Z")
        self.assertEqual(payload["nodes"][0]["supertype"], EntityType.DEPARTMENT.supertype)
        self.assertEqual(payload["nodes"][0]["evidence_ids"], ["obs-1"])
        self.assertEqual(payload["edges"][0]["edge_id"], "edge-1")
        self.assertEqual(payload["evidence"][0]["id"], "obs-1")

        restored = Graph.from_v1(payload)
        self.assertEqual(restored.schema_version, "2.0.0")
        self.assertEqual(restored.nodes[0].type, EntityType.DEPARTMENT)
        self.assertEqual(restored.nodes[0].evidence_ids, ["obs-1"])
        self.assertEqual(restored.edges[0].edge_id, "edge-1")
        self.assertEqual(restored.evidence[0].id, "obs-1")

    def test_from_v1_accepts_node_evidence_ids_when_present(self):
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "label": "Sales",
                    "type": "Department",
                    "details": {"what": "..."},
                    "evidence_ids": ["obs-7", "obs-9"],
                }
            ],
            "edges": [],
            "evidence": [
                {
                    "id": "obs-7",
                    "type": "observation",
                    "source": "engram",
                    "content": "Sales evidence",
                    "timestamp": "",
                }
            ],
        }

        graph = Graph.from_v1(payload)
        self.assertEqual(graph.nodes[0].evidence_ids, ["obs-7", "obs-9"])


if __name__ == "__main__":
    unittest.main()
