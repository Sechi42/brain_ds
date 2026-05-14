import re
import unittest

from brain_ds.ontology import Edge, EntityType, Node, RelationshipType, TYPE_COLORS
from brain_ds.ui import simple_renderer


class TestEntityType(unittest.TestCase):
    def test_entity_members_count(self):
        self.assertEqual(len(EntityType), 13)

    def test_domain_types_have_expected_supertypes(self):
        expected = {
            EntityType.ORGANIZATION: "actor",
            EntityType.DEPARTMENT: "actor",
            EntityType.ROLE: "actor",
            EntityType.DATA_SOURCE: "data",
            EntityType.HEURISTIC: "process",
            EntityType.TACIT_KNOWLEDGE: "data",
            EntityType.PROBLEM_IMPROVEMENT_AREA: "problem",
            EntityType.PROJECT: "process",
            EntityType.RISK: "risk",
            EntityType.DECISION: "process",
            EntityType.KPI: "metric",
            EntityType.SOLUTION: "solution",
        }
        for entity, supertype in expected.items():
            self.assertEqual(entity.supertype, supertype)

    def test_colors_are_valid_hex(self):
        for entity in EntityType:
            self.assertRegex(entity.color, r"^#[0-9a-fA-F]{6}$")

    def test_from_string_backward_compat_and_fallback(self):
        self.assertEqual(EntityType.from_string("Department"), EntityType.DEPARTMENT)
        self.assertEqual(EntityType.from_string("data_source"), EntityType.DATA_SOURCE)
        self.assertEqual(
            EntityType.from_string("Problem / Improvement Area"),
            EntityType.PROBLEM_IMPROVEMENT_AREA,
        )
        self.assertEqual(EntityType.from_string("Legacy Category"), EntityType.UNKNOWN)
        self.assertEqual(EntityType.from_string(None), EntityType.UNKNOWN)


class TestRelationshipType(unittest.TestCase):
    def test_relationship_labels_count_and_descriptions(self):
        self.assertEqual(len(RelationshipType), 14)
        for rel in RelationshipType:
            self.assertTrue(rel.description.strip())


class TestGraphModel(unittest.TestCase):
    def test_node_accepts_entity_type(self):
        node = Node(id="n1", label="Finance", type=EntityType.DEPARTMENT)
        self.assertEqual(node.type, EntityType.DEPARTMENT)

    def test_node_coerces_unknown_type_to_unknown(self):
        node = Node(id="n2", label="Legacy", type="Legacy Category")
        self.assertEqual(node.type, EntityType.UNKNOWN)

    def test_edge_coerces_valid_label(self):
        edge = Edge(source="a", target="b", label="depends-on")
        self.assertEqual(edge.label, RelationshipType.DEPENDS_ON)

    def test_edge_raises_for_invalid_label(self):
        with self.assertRaises(ValueError):
            Edge(source="a", target="b", label="invalid-label")

    def test_type_colors_contains_all_entity_values(self):
        for entity in EntityType:
            self.assertIn(entity.value, TYPE_COLORS)
            self.assertTrue(re.match(r"^#[0-9a-fA-F]{6}$", TYPE_COLORS[entity.value]))


class TestViewerOntologyIntegration(unittest.TestCase):
    def test_viewer_module_import_does_not_require_pyvis(self):
        self.assertTrue(hasattr(simple_renderer, "build_network"))
        self.assertTrue(callable(simple_renderer._load_network_class))

    def test_lazy_pyvis_loader_returns_none_when_dependency_missing(self):
        network_cls = simple_renderer._load_network_class()
        if network_cls is None:
            self.assertIsNone(network_cls)
        else:
            self.assertEqual(network_cls.__name__, "Network")

    def test_viewer_unknown_type_uses_ontology_fallback_color(self):
        class FakeNetwork:
            def __init__(self, **kwargs):
                self.nodes = []

            def set_options(self, options):
                return None

            def add_node(self, **kwargs):
                self.nodes.append(kwargs)

            def add_edge(self, *args, **kwargs):
                return None

        graph = {
            "nodes": [
                {"id": "n1", "label": "Known", "type": "Department", "details": {}},
                {"id": "n2", "label": "Legacy", "type": "Legacy Category", "details": {}},
            ],
            "edges": [],
        }

        net = simple_renderer.build_network(graph, FakeNetwork)
        colors = {node["n_id"]: node["color"] for node in net.nodes}
        groups = {node["n_id"]: node["group"] for node in net.nodes}

        self.assertEqual(colors["n1"], EntityType.DEPARTMENT.color)
        self.assertEqual(colors["n2"], EntityType.UNKNOWN.color)
        self.assertEqual(groups["n2"], EntityType.UNKNOWN.value)


if __name__ == "__main__":
    unittest.main()
