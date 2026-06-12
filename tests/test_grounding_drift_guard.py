"""Drift guard for the MCP grounding harness.

The grounding module (``brain_ds/mcp/grounding.py``) mixes two kinds of context:

* Category-1 context is *derived at runtime* from the ontology enums, so it can
  never drift.
* Category-2 context is *hand-maintained* Python constants that reference entity
  types by their literal string value (question banks, write templates, BRD
  fingerprints). These DO drift: adding or renaming an ``EntityType`` silently
  leaves the Category-2 constants stale, and the harness returns context that no
  longer matches the ontology.

These tests make that drift a hard failure instead of a silent one. When they go
red, update ``brain_ds/mcp/grounding.py`` (and the skill prose it mirrors) so the
harness stays in sync. See the "Harness maintenance" section in ``CLAUDE.md``.
"""

from __future__ import annotations

import unittest
from typing import Any, cast

from brain_ds.mcp import grounding
from brain_ds.ontology.entity_types import EntityType
from brain_ds.scoring import similarity
from brain_ds.store.models import NodeRow

# EntityTypes that intentionally have NO elicitation question bank entry.
# Adding a new EntityType that should be elicited means adding it to
# QUESTION_BANK; adding one that should not means listing it here. Either way
# the choice is explicit and reviewed.
ELICIT_EXEMPT_TYPES: frozenset[str] = frozenset(
    {
        "Project",  # captured via map/brd synthesis, not the elicit interview
        "Risk",  # derived during mapping, not directly elicited
        "Unknown",  # fallback bucket, never elicited
    }
)


def _entity_values() -> set[str]:
    return {e.value for e in EntityType}


class GroundingEntityNameValidityTests(unittest.TestCase):
    """Every hand-maintained entity-name string must be a real EntityType value.

    This catches renames and typos: rename an EntityType in the ontology and any
    stale Category-2 reference fails here, pointing straight at what to fix.
    """

    def test_question_bank_keys_are_valid_entity_types(self) -> None:
        invalid = set(grounding.QUESTION_BANK) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"QUESTION_BANK references unknown entity types: {sorted(invalid)}",
        )

    def test_node_write_template_type_keys_are_valid_entity_types(self) -> None:
        # "generic" is the shared fallback template, not an entity type.
        type_keys = set(grounding.NODE_WRITE_TEMPLATES) - {"generic"}
        invalid = type_keys - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"NODE_WRITE_TEMPLATES references unknown entity types: {sorted(invalid)}",
        )

    def test_dataset_fingerprint_order_entries_are_valid_entity_types(self) -> None:
        fingerprint = cast(list[str], grounding.COMPLETENESS_MATRIX_TEMPLATE["dataset_fingerprint_order"])
        invalid = set(fingerprint) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"dataset_fingerprint_order references unknown entity types: {sorted(invalid)}",
        )


class GroundingEntityCoverageTests(unittest.TestCase):
    """Every EntityType must be consciously handled by the elicit harness.

    Add a new EntityType to the ontology and this fails until you either give it
    a QUESTION_BANK entry or explicitly exempt it in ELICIT_EXEMPT_TYPES. That is
    the self-maintaining contract: new context cannot land without the harness
    being updated to acknowledge it.
    """

    def test_every_entity_type_is_elicited_or_exempt(self) -> None:
        covered = set(grounding.QUESTION_BANK) | set(ELICIT_EXEMPT_TYPES)
        missing = _entity_values() - covered
        self.assertEqual(
            missing,
            set(),
            (
                "These EntityTypes are neither in grounding.QUESTION_BANK nor "
                f"ELICIT_EXEMPT_TYPES: {sorted(missing)}. Add a question bank entry "
                "or exempt them, then update the mirrored skill prose."
            ),
        )

    def test_exempt_types_are_real_and_not_double_listed(self) -> None:
        # Exemptions must be valid entity types...
        invalid = set(ELICIT_EXEMPT_TYPES) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"ELICIT_EXEMPT_TYPES lists unknown entity types: {sorted(invalid)}",
        )
        # ...and must not also carry a question bank entry (contradictory state).
        contradictory = set(ELICIT_EXEMPT_TYPES) & set(grounding.QUESTION_BANK)
        self.assertEqual(
            contradictory,
            set(),
            f"Types are both exempt and in QUESTION_BANK: {sorted(contradictory)}",
        )


class GroundingDataSourceCompletenessTests(unittest.TestCase):
    """Data Source question bank and write template must cover concrete structure
    identifiers so the harness cannot silently drift from the skill prose contract.
    """

    def test_data_source_question_bank_covers_structure_identifiers(self) -> None:
        questions = " ".join(grounding.QUESTION_BANK.get("Data Source", []))
        required_topics = [
            "database and tables",
            "workbook and sheets",
            "columns/fields",
            "used for",
            "owns or manages",
            "refreshed or updated",
        ]
        for topic in required_topics:
            with self.subTest(topic=topic):
                self.assertIn(topic, questions)

    def test_data_source_write_template_captures_structure(self) -> None:
        ds_template = cast(dict[str, Any], grounding.NODE_WRITE_TEMPLATES.get("Data Source", {}))
        learned = cast(dict[str, str], ds_template.get("details", {})).get("learned", "")
        required_fields = [
            "Kind:",
            "System:",
            "Database:",
            "Tables/Sheets:",
            "Key Columns/Fields:",
            "Purpose:",
            "Owner:",
            "Refresh:",
            "Trust:",
        ]
        for field in required_fields:
            with self.subTest(field=field):
                self.assertIn(field, learned)


def _node(node_id: str, label: str, type_: str, details: dict | None = None) -> NodeRow:
    return NodeRow(
        graph_id="g",
        id=node_id,
        label=label,
        type=type_,
        supertype=None,
        details=details if details is not None else {"where": "somewhere real", "learned": "ok"},
        card_sections=None,
        editable_fields=None,
        evidence_ids=None,
        layout_hint=None,
        parent_id=None,
        depth=0,
        created_at="2026-01-01T00:00:00Z",
        modified_at="2026-01-01T00:00:00Z",
    )


class SuggestConnectionsHardeningTests(unittest.TestCase):
    """Regression guards for the suggest_connections hardening: Spanish stopwords
    must never justify an edge, "shared-with" must be earned, and sparse nodes
    must arrive blocked instead of edge-ready.
    """

    def test_spanish_stopword_overlap_produces_no_suggestion(self) -> None:
        # Two unmapped-pair nodes whose only textual overlap is Spanish filler
        # ("de", "la", "y", "para") plus the accented "también" that used to
        # leak a garbage "n" token. No suggestion may survive.
        focus = _node(
            "R-1",
            "Coordinación de la operación y para el control",
            "Role",
            {"where": "área también de control", "learned": "ok"},
        )
        other = _node(
            "R-2",
            "Gestión de la calidad y para el área",
            "Role",
            {"where": "zona también de calidad", "learned": "ok"},
        )
        result = similarity.suggest_connections_for_node([focus, other], [], "R-1")
        self.assertEqual(result["suggestions"], [])

    def test_default_threshold_is_hardened(self) -> None:
        self.assertGreaterEqual(similarity.DEFAULT_THRESHOLD, 0.55)
        self.assertGreaterEqual(similarity.DEFAULT_MIN_SHARED_TOKENS, 2)

    def test_no_type_pair_rule_maps_to_shared_with_unless_symmetric(self) -> None:
        offenders = [
            (sorted(pair), label)
            for pair, (_s, _t, label) in similarity.TYPE_PAIR_SUGGESTIONS.items()
            if label == "shared-with" and len(pair) > 1
        ]
        self.assertEqual(
            offenders,
            [],
            f"Asymmetric type pairs must not fall back to shared-with: {offenders}",
        )

    def test_underspecified_node_is_blocked_as_review_needed(self) -> None:
        focus = _node(
            "DS-1",
            "Contpaq ventas mensuales facturación",
            "Data Source",
            {"where": "", "learned": "Underspecified: faltan tablas, columnas clave, dueño"},
        )
        other = _node(
            "ROLE-1",
            "Analista ventas mensuales facturación Contpaq",
            "Role",
            {"where": "ventas mensuales facturación Contpaq", "learned": "ok"},
        )
        self.assertTrue(similarity.is_sparse(focus))
        result = similarity.suggest_connections_for_node([focus, other], [], "DS-1")
        self.assertEqual(result["suggestions"][0]["suggested_edge"]["label"], "review-needed")
        self.assertIn("sparse", result["suggestions"][0]["reason"])
        self.assertEqual(result["blocked_sparse"], 1)

    def test_completeness_gate_is_in_map_connections_payload(self) -> None:
        payload = grounding.map_connections_context()
        gate = payload.get("completeness_gate")
        self.assertIsInstance(gate, dict)
        self.assertEqual(gate["tool"], "assess_completeness")


class AssessCompletenessTests(unittest.TestCase):
    """The pre-mapping gate must recommend elicitation for hollow graphs and
    flag underspecified nodes for documentation."""

    def test_hollow_graph_recommends_elicit(self) -> None:
        from brain_ds.mcp.completeness import assess_graph_completeness

        nodes = [
            _node("ORG-1", "Grupo Topete", "Organization"),
            _node("R-1", "Director", "Role"),
        ]
        result = assess_graph_completeness(nodes)
        self.assertEqual(result["pre_mapping_recommendation"], "elicit")
        self.assertGreaterEqual(result["missing_count"], 3)
        self.assertIn("Department", result["missing_for_brd"])

    def test_underspecified_nodes_recommend_document(self) -> None:
        from brain_ds.mcp.completeness import assess_graph_completeness
        from brain_ds.ontology.entity_types import EntityType as ET

        nodes = [_node(f"N-{i}", f"Node {i}", e.value) for i, e in enumerate(ET) if e is not ET.UNKNOWN]
        nodes.append(
            _node("DS-X", "Contpaq", "Data Source", {"where": "", "learned": "Underspecified: faltan tablas"})
        )
        result = assess_graph_completeness(nodes)
        self.assertEqual(result["pre_mapping_recommendation"], "document")
        self.assertIn("DS-X", result["underspecified_nodes"])
        self.assertEqual(result["completeness_matrix"]["Data Source"], "sparse")

    def test_grounded_graph_proceeds(self) -> None:
        from brain_ds.mcp.completeness import assess_graph_completeness
        from brain_ds.ontology.entity_types import EntityType as ET

        nodes = [_node(f"N-{i}", f"Node {i}", e.value) for i, e in enumerate(ET) if e is not ET.UNKNOWN]
        result = assess_graph_completeness(nodes)
        self.assertEqual(result["pre_mapping_recommendation"], "proceed_with_gaps")
        self.assertEqual(result["missing_for_brd"], [])


if __name__ == "__main__":
    unittest.main()
