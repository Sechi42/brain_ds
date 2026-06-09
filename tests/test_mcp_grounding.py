from __future__ import annotations

import unittest

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.scoring.engine import ScoringEngine

# These imports will fail (RED) until brain_ds/mcp/grounding.py is created (Task 1.2 / 1.4 / 1.6).
from brain_ds.mcp.grounding import (
    QUESTION_BANK,
    ORG_SLUG_RULES,
    TOPIC_KEY_FORMAT,
    MEM_SAVE_TEMPLATES,
    CONNECTION_RULES,
    BRD_SECTION_ORDER,
    SECTION_RULES,
    COMPLETENESS_MATRIX_TEMPLATE,
    build_entity_types,
    build_supertypes,
    build_expected_sections,
    build_relationship_types,
    build_base_weights,
    build_relationship_labels,
    build_scoring_factors,
    elicit_context,
    map_connections_context,
    generate_brd_context,
)


class TestCat1Builders(unittest.TestCase):
    """Task 1.1 — Cat-1 builder tests (derive from live enums)."""

    def test_entity_types_all_present(self) -> None:
        result = build_entity_types()
        values = {d["value"] for d in result}
        self.assertEqual(values, {e.value for e in EntityType})

    def test_entity_types_count_matches_enum(self) -> None:
        result = build_entity_types()
        self.assertEqual(len(result), len(list(EntityType)))

    def test_supertypes_all_unique_sorted(self) -> None:
        result = build_supertypes()
        self.assertEqual(result, sorted(result))
        self.assertGreater(len(result), 0)
        # All values must be unique
        self.assertEqual(len(result), len(set(result)))

    def test_expected_sections_top_level_matches_per_entity(self) -> None:
        result = build_expected_sections()
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), {e.value for e in EntityType})

    def test_relationship_types_all_present(self) -> None:
        result = build_relationship_types()
        self.assertEqual(len(result), len(list(RelationshipType)))

    def test_base_weights_14_entries_string_keyed(self) -> None:
        result = build_base_weights()
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), {r.value for r in RelationshipType})

    def test_relationship_labels_count_matches_enum(self) -> None:
        result = build_relationship_labels()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), len(list(RelationshipType)))

    def test_scoring_factors_count_matches_engine(self) -> None:
        result = build_scoring_factors()
        engine = ScoringEngine()
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), len(engine.factor_weights))


class TestCat2Accessors(unittest.TestCase):
    """Task 1.3 — Cat-2 accessor presence tests."""

    def test_question_bank_has_10_keys(self) -> None:
        self.assertIsInstance(QUESTION_BANK, dict)
        self.assertEqual(len(QUESTION_BANK), 10)

    def test_org_slug_rules_nonempty(self) -> None:
        self.assertTrue(ORG_SLUG_RULES)

    def test_topic_key_format_nonempty(self) -> None:
        self.assertIsInstance(TOPIC_KEY_FORMAT, str)
        self.assertTrue(TOPIC_KEY_FORMAT)

    def test_mem_save_templates_nonempty_dict(self) -> None:
        self.assertIsInstance(MEM_SAVE_TEMPLATES, dict)
        self.assertGreater(len(MEM_SAVE_TEMPLATES), 0)

    def test_connection_rules_nonempty(self) -> None:
        self.assertTrue(CONNECTION_RULES)

    def test_brd_section_order_14_entries(self) -> None:
        self.assertIsInstance(BRD_SECTION_ORDER, list)
        self.assertEqual(len(BRD_SECTION_ORDER), 14)

    def test_section_rules_nonempty(self) -> None:
        self.assertTrue(SECTION_RULES)

    def test_completeness_matrix_template_nonempty(self) -> None:
        self.assertTrue(COMPLETENESS_MATRIX_TEMPLATE)


class TestComposerReturnShapes(unittest.TestCase):
    """Task 1.5 — composer return-shape tests."""

    def test_elicit_context_has_all_9_keys(self) -> None:
        result = elicit_context()
        expected_keys = {
            "entity_types",
            "supertypes",
            "expected_sections",
            "relationship_types",
            "base_weights",
            "question_bank",
            "org_slug_rules",
            "topic_key_format",
            "mem_save_templates",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_map_connections_context_has_4_keys(self) -> None:
        result = map_connections_context()
        expected_keys = {
            "entity_types",
            "connection_rules",
            "relationship_labels",
            "scoring_factors",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_generate_brd_context_has_4_keys(self) -> None:
        result = generate_brd_context()
        expected_keys = {
            "entity_types",
            "brd_section_order",
            "section_rules",
            "completeness_matrix_template",
        }
        self.assertEqual(set(result.keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()
