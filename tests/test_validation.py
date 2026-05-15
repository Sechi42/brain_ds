import copy
import unittest

from brain_ds.demo import build_logitrans_graph
from brain_ds.ontology import Graph
from brain_ds.validation import ValidationError, ValidationResult, validate_graph


def _valid_graph() -> dict:
    return {
        "schema_version": "2.0.0",
        "org": "acme",
        "nodes": [
            {
                "id": "n1",
                "label": "Operations",
                "type": "Department",
                "evidence_ids": ["ev-1"],
            },
            {
                "id": "n2",
                "label": "Lead",
                "type": "Role",
                "evidence_ids": ["ev-1"],
            },
        ],
        "edges": [
            {
                "edge_id": "e1",
                "source": "n1",
                "target": "n2",
                "label": "depends-on",
                "evidence_ids": ["ev-1"],
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "type": "observation",
                "source": "engram",
                "content": "Observed dependency",
            }
        ],
    }


class TestValidationResultContract(unittest.TestCase):
    def test_result_and_error_dataclasses_have_expected_fields(self):
        error = ValidationError(
            path="nodes[0].type",
            message="Unknown type",
            severity="error",
            suggestion="Did you mean 'Department'?",
        )
        result = ValidationResult(is_valid=False, errors=[error], warnings=[], normalized={})

        self.assertEqual(error.path, "nodes[0].type")
        self.assertEqual(error.message, "Unknown type")
        self.assertEqual(error.severity, "error")
        self.assertEqual(error.suggestion, "Did you mean 'Department'?")
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.normalized, {})


class TestValidateGraph(unittest.TestCase):
    def test_required_top_level_fields(self):
        data = {"schema_version": "2.0.0", "nodes": [], "edges": []}

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "org" for err in result.errors))

    def test_required_node_and_edge_fields(self):
        data = _valid_graph()
        data["nodes"] = [{"id": "n1", "label": "Node without type"}]
        data["edges"] = [{"source": "n1", "target": "n1"}]

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "nodes[0].type" for err in result.errors))
        self.assertTrue(any(err.path == "edges[0].label" for err in result.errors))

    def test_duplicate_node_ids_and_edge_ids(self):
        data = _valid_graph()
        data["nodes"].append({"id": "n1", "label": "Duplicate", "type": "Department"})
        data["edges"].append({"edge_id": "e1", "source": "n1", "target": "n2", "label": "uses"})

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "nodes[2].id" for err in result.errors))
        self.assertTrue(any(err.path == "edges[1].edge_id" for err in result.errors))

    def test_broken_edge_cross_references(self):
        data = _valid_graph()
        data["edges"][0]["source"] = "missing"

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "edges[0].source" for err in result.errors))

    def test_unsupported_entity_type_has_actionable_suggestion(self):
        data = _valid_graph()
        data["nodes"][0]["type"] = "Company"

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        matching = [err for err in result.errors if err.path == "nodes[0].type"]
        self.assertEqual(len(matching), 1)
        self.assertIn("Did you mean", matching[0].suggestion or "")

    def test_unsupported_relationship_type_is_strict(self):
        data = _valid_graph()
        data["edges"][0]["label"] = "DEPENDS_ON"

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "edges[0].label" for err in result.errors))

    def test_evidence_integrity_checks_node_and_edge_references(self):
        data = _valid_graph()
        data["nodes"][0]["evidence_ids"] = ["missing-1"]
        data["edges"][0]["evidence_ids"] = ["missing-2"]

        result = validate_graph(data)

        self.assertFalse(result.is_valid)
        self.assertTrue(any(err.path == "nodes[0].evidence_ids[0]" for err in result.errors))
        self.assertTrue(any(err.path == "edges[0].evidence_ids[0]" for err in result.errors))

    def test_safe_normalization_returns_new_dict_and_keeps_input_unmodified(self):
        data = _valid_graph()
        data["nodes"][0]["type"] = "department"
        before = copy.deepcopy(data)

        result = validate_graph(data)

        self.assertTrue(result.is_valid)
        self.assertEqual(data, before)
        self.assertEqual(result.normalized["nodes"][0]["type"], "Department")

    def test_empty_graph_warns_without_errors(self):
        data = {
            "schema_version": "2.0.0",
            "org": "acme",
            "nodes": [],
            "edges": [],
            "evidence": [],
        }

        result = validate_graph(data)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])
        self.assertGreater(len(result.warnings), 0)


class TestValidationAcceptance(unittest.TestCase):
    def test_logitrans_demo_graph_validates_without_errors(self):
        graph_dict = build_logitrans_graph().to_dict()

        result = validate_graph(graph_dict)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_roundtrip_validate_normalize_from_v1_to_dict_revalidate(self):
        graph_dict = build_logitrans_graph().to_dict()

        initial = validate_graph(graph_dict)
        self.assertTrue(initial.is_valid)

        restored = Graph.from_v1(initial.normalized)
        roundtrip = validate_graph(restored.to_dict())

        self.assertTrue(roundtrip.is_valid)
        self.assertEqual(roundtrip.errors, [])


if __name__ == "__main__":
    unittest.main()
