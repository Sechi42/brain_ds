import unittest

from brain_ds.demo import build_logitrans_graph
from brain_ds.ontology import EntityType, Graph, RelationshipType
from brain_ds.ui.render_context import build_render_context
from brain_ds.ui.template_renderer import render_interactive_html


class TestSmokeLogiTransDemo(unittest.TestCase):
    def test_build_logitrans_graph_returns_valid_graph(self):
        graph = build_logitrans_graph()

        self.assertIsInstance(graph, Graph)
        self.assertEqual(graph.org, "logitrans")
        self.assertTrue(graph.nodes)
        self.assertTrue(graph.edges)

        present_types = {node.type for node in graph.nodes}
        self.assertIn(EntityType.DEPARTMENT, present_types)
        self.assertIn(EntityType.ROLE, present_types)
        self.assertIn(EntityType.KPI, present_types)
        self.assertIn(EntityType.DECISION, present_types)
        self.assertIn(EntityType.DATA_SOURCE, present_types)
        self.assertIn(EntityType.HEURISTIC, present_types)

    def test_graph_to_dict_roundtrip(self):
        graph = build_logitrans_graph()
        data = graph.to_dict()

        self.assertIn("schema_version", data)
        self.assertIn("org", data)
        self.assertIn("generated_at", data)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("evidence", data)

        roundtrip = Graph.from_v1(data)
        self.assertEqual(len(roundtrip.nodes), len(graph.nodes))
        self.assertEqual(len(roundtrip.edges), len(graph.edges))

    def test_build_render_context(self):
        graph = build_logitrans_graph()
        context = build_render_context(graph)

        self.assertIn("meta", context)
        self.assertIn("nodes", context)
        self.assertIn("edges", context)
        self.assertIn("type_groups", context)
        self.assertIn("adjacency", context)
        self.assertEqual(context["meta"]["org"], "logitrans")

    def test_render_interactive_html_contains_markers(self):
        graph = build_logitrans_graph()
        context = build_render_context(graph)
        html = render_interactive_html(context)

        self.assertIn("logitrans", html.lower())
        self.assertIn("vis-network", html)
        self.assertIn("nodes", html.lower())

    def test_deterministic(self):
        first = build_logitrans_graph().to_dict()
        second = build_logitrans_graph().to_dict()
        self.assertEqual(first, second)

    def test_relationship_types_are_canonical(self):
        graph = build_logitrans_graph()
        labels = {edge.label for edge in graph.edges}
        self.assertIn(RelationshipType.OWNS, labels)
        self.assertIn(RelationshipType.MEASURED_BY, labels)
        self.assertIn(RelationshipType.USES, labels)
        self.assertIn(RelationshipType.DEPENDS_ON, labels)
