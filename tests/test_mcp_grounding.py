from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.scoring.engine import ScoringEngine

# These imports will fail (RED) until brain_ds/mcp/grounding.py is created (Task 1.2 / 1.4 / 1.6).
from brain_ds.mcp.grounding import (
    QUESTION_BANK,
    ORG_SLUG_RULES,
    NODE_ID_FORMAT,
    NODE_WRITE_TEMPLATES,
    CONNECTION_RULES,
    SECRET_CONNECTION_RULES,
    BRD_SECTION_ORDER,
    SECTION_RULES,
    COMPLETENESS_MATRIX_TEMPLATE,
    ARTIFACT_CONTRACT,
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

    def test_node_id_format_nonempty(self) -> None:
        self.assertIsInstance(NODE_ID_FORMAT, str)
        self.assertTrue(NODE_ID_FORMAT)

    def test_node_write_templates_nonempty_dict(self) -> None:
        self.assertIsInstance(NODE_WRITE_TEMPLATES, dict)
        self.assertGreater(len(NODE_WRITE_TEMPLATES), 0)

    def test_question_bank_prioritizes_data_source_before_department_and_role(self) -> None:
        ordered_keys = list(QUESTION_BANK.keys())
        data_source_index = ordered_keys.index("Data Source")
        department_index = ordered_keys.index("Department")
        role_index = ordered_keys.index("Role")
        self.assertLess(data_source_index, department_index)
        self.assertLess(data_source_index, role_index)

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

    def test_elicit_context_has_all_16_keys_legacy(self) -> None:
        result = elicit_context()
        expected_keys = {
            "entity_types",
            "supertypes",
            "expected_sections",
            "relationship_types",
            "base_weights",
            "question_bank",
            "org_slug_rules",
            "node_id_format",
            "node_write_templates",
            "workflow",
            "source_exploration_contract",
            "delegation_protocol",
            "pipeline_stages",
            "intake_paths",
            "artifact_contract",
            "deliverable_contract",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_elicit_workflow_mandates_dual_persistence(self) -> None:
        result = elicit_context()
        workflow = cast(dict[str, Any], result["workflow"])
        steps = " ".join(cast(list[str], workflow["steps"]))
        self.assertIn("update_node", steps)
        self.assertIn("mem_save", steps)
        self.assertIn("suggest_connections", steps)
        self.assertIn("single source of truth", cast(str, workflow["dual_persistence"]))
        self.assertIn("Never represent the org graph in local files", cast(str, workflow["anti_drift"]))

    def test_elicit_context_omits_legacy_engram_keys(self) -> None:
        result = elicit_context()
        self.assertNotIn("topic_key_format", result)
        self.assertNotIn("mem_save_templates", result)

    def test_map_connections_context_has_13_keys_legacy(self) -> None:
        result = map_connections_context()
        expected_keys = {
            "entity_types",
            "connection_rules",
            "completeness_gate",
            "two_phase_mapping",
            "relationship_labels",
            "scoring_factors",
            "retrieval_contract",
            "rag_workflow",
            "source_exploration_contract",
            "delegation_protocol",
            "pipeline_stages",
            "intake_paths",
            "artifact_contract",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_map_connections_context_retrieval_contract_mentions_sqlite_queries(self) -> None:
        result = map_connections_context()
        retrieval_contract = cast(str, result["retrieval_contract"])
        self.assertIn("suggest_connections(graph_id=<slug>, node_id=<id>)", retrieval_contract)
        self.assertIn("list_nodes(graph_id=<slug>, type=<EntityType>)", retrieval_contract)
        self.assertIn("search_graph(graph_id=<slug>, query=<text>)", retrieval_contract)
        self.assertIn("typed SQL filters are not equivalent to Engram substring search", retrieval_contract)

    def test_map_rag_workflow_routes_linking_through_suggest_connections(self) -> None:
        result = map_connections_context()
        rag_workflow = cast(dict[str, Any], result["rag_workflow"])
        steps = " ".join(cast(list[str], rag_workflow["steps"]))
        self.assertIn("suggest_connections", steps)
        self.assertIn("add_edge", steps)
        self.assertIn("Never bulk-read the whole graph", steps)
        self.assertIn("thousands of nodes", cast(str, rag_workflow["scaling_contract"]))

    def test_generate_brd_context_has_11_keys_legacy(self) -> None:
        result = generate_brd_context()
        expected_keys = {
            "entity_types",
            "brd_section_order",
            "section_rules",
            "completeness_matrix_template",
            "retrieval_contract",
            "brd_graph_persistence_contract",
            "strict_mode",
            "delegation_protocol",
            "pipeline_stages",
            "intake_paths",
            "artifact_contract",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_brd_graph_persistence_contract_matches_ui_panel_convention(self) -> None:
        """The contract must mirror brain_ds/ui/src/panels/brd-panel.ts exactly."""
        result = generate_brd_context()
        contract = cast(dict[str, Any], result["brd_graph_persistence_contract"])
        template = cast(dict[str, Any], contract["update_node_template"])
        self.assertEqual(template["node_id"], "brd-<org-slug>")
        self.assertEqual(template["label"], "BRD")
        self.assertEqual(template["type"], "Unknown")
        sections = cast(list[dict[str, Any]], template["card_sections"])
        self.assertEqual(sections[0]["title"], "Contenido")
        self.assertEqual(sections[0]["order"], 0)
        self.assertIn("update_node", cast(str, contract["when"]))

    def test_brainds_docs_brd_carveout_matches_contract(self) -> None:
        result = generate_brd_context()
        contract = cast(dict[str, Any], result["brd_graph_persistence_contract"])
        template = cast(dict[str, Any], contract["update_node_template"])
        sections = cast(list[dict[str, Any]], template["card_sections"])
        main_section = sections[0]
        self.assertEqual(main_section["order"], 0)
        self.assertEqual(main_section["icon"], "")

        repo_root = Path(__file__).resolve().parents[1]
        skill_paths = [
            repo_root / "skills" / "brainds-docs" / "SKILL.md",
            repo_root / ".opencode" / "skills" / "brainds-docs" / "SKILL.md",
        ]
        for skill_path in skill_paths:
            with self.subTest(skill_path=str(skill_path)):
                content = skill_path.read_text(encoding="utf-8")
                self.assertIn("order: 0", content)
                self.assertIn('icon: ""', content)
                self.assertIn("BRD_GRAPH_PERSISTENCE_CONTRACT", content)

    def test_delegation_protocol_present_in_all_composers(self) -> None:
        for payload in (elicit_context(), map_connections_context(), generate_brd_context()):
            protocol = cast(dict[str, Any], payload["delegation_protocol"])
            self.assertIn("sub-agents", cast(str, protocol["role"]))
            self.assertIn("engram", cast(str, protocol["session_setup"]))
            self.assertIn(".elicit", cast(str, protocol["session_setup"]))
            flow = " ".join(cast(list[str], protocol["source_exploration_flow"]))
            self.assertIn("magnitude scan", flow)
            self.assertIn("non-overlapping", flow)
            self.assertIn("update_node", flow)
            self.assertIn("brain_ds-owned skills", cast(str, protocol["skill_scope"]))

    def test_generate_brd_context_retrieval_contract_mentions_seeded_vault_validation(self) -> None:
        result = generate_brd_context()
        retrieval_contract = cast(str, result["retrieval_contract"])
        self.assertIn("list_nodes(graph_id=<slug>, type=<EntityType>)", retrieval_contract)
        self.assertIn("search_graph(graph_id=<slug>, query=<text>)", retrieval_contract)
        self.assertIn("validate retrieval changes on a seeded vault", retrieval_contract)

    # T1-3/T1-4/T1-8: bump key counts 14→16, 12→13, 10→11 (artifact_contract + deliverable_contract injected)
    # PR4-T1: counts bumped again 16→17, 13→14, 11→12 (secret_connection_rules injected)
    def test_elicit_context_has_all_17_keys(self) -> None:
        result = elicit_context()
        self.assertIn("artifact_contract", result)
        self.assertIn("deliverable_contract", result)
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(len(result), 17)

    def test_map_connections_context_has_14_keys(self) -> None:
        result = map_connections_context()
        self.assertIn("artifact_contract", result)
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(len(result), 14)

    def test_generate_brd_context_has_12_keys(self) -> None:
        result = generate_brd_context()
        self.assertIn("artifact_contract", result)
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(len(result), 12)


class TestArtifactContract(unittest.TestCase):
    """T1-1/T1-2: ARTIFACT_CONTRACT constant shape."""

    def test_artifact_contract_has_four_phase_keys(self) -> None:
        self.assertIsInstance(ARTIFACT_CONTRACT, dict)
        for key in ("source-docs", "map", "brd", "verify"):
            self.assertIn(key, ARTIFACT_CONTRACT, f"ARTIFACT_CONTRACT missing key '{key}'")

    def test_artifact_contract_each_phase_entry_has_required_keys(self) -> None:
        phase_keys = ("source-docs", "map", "brd", "verify")
        for phase in phase_keys:
            entry = ARTIFACT_CONTRACT[phase]
            with self.subTest(phase=phase):
                self.assertIn("required_keys", entry, f"{phase} missing 'required_keys'")
                self.assertIn("validator", entry, f"{phase} missing 'validator'")

    def test_artifact_contract_required_keys_include_artifact_type(self) -> None:
        phase_keys = ("source-docs", "map", "brd", "verify")
        for phase in phase_keys:
            entry = ARTIFACT_CONTRACT[phase]
            with self.subTest(phase=phase):
                self.assertIn(
                    "artifact_type",
                    entry["required_keys"],
                    f"{phase}.required_keys must include 'artifact_type'",
                )

    def test_artifact_contract_map_has_completeness_gate_key(self) -> None:
        map_entry = ARTIFACT_CONTRACT["map"]
        self.assertIn("completeness_gate", map_entry["required_keys"])

    def test_artifact_contract_verify_has_gate_key(self) -> None:
        verify_entry = ARTIFACT_CONTRACT["verify"]
        self.assertIn("gate", verify_entry["required_keys"])

    def test_artifact_contract_brd_has_brd_node_key(self) -> None:
        brd_entry = ARTIFACT_CONTRACT["brd"]
        self.assertIn("brd_node", brd_entry["required_keys"])


class TestSecretConnectionRules(unittest.TestCase):
    """PR4-T1 — SECRET_CONNECTION_RULES constant shape + payload wiring.

    These tests enforce the three spec requirements for PR4:
    1. SECRET_CONNECTION_RULES exists as an importable constant with the 6-step recipe.
    2. It appears in all three grounding tool payloads.
    3. It explicitly forbids list_secret_handles and teaches the correct flow.
    """

    def test_secret_connection_rules_is_string(self) -> None:
        """Constant exists and is a non-empty string."""
        self.assertIsInstance(SECRET_CONNECTION_RULES, str)
        self.assertTrue(SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_forbids_list_secret_handles(self) -> None:
        """Must explicitly say agents must NOT call list_secret_handles."""
        self.assertIn("list_secret_handles", SECRET_CONNECTION_RULES)
        # Rule must forbid it (keyword "NEVER" or "NOT" or "admin-only" nearby)
        self.assertIn("NEVER", SECRET_CONNECTION_RULES.upper())

    def test_secret_connection_rules_teaches_list_source_connections(self) -> None:
        """Must teach list_source_connections as the discovery step."""
        self.assertIn("list_source_connections", SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_teaches_explore_source(self) -> None:
        """Must reference explore_source as the connection step."""
        self.assertIn("explore_source", SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_covers_aws_postgres(self) -> None:
        """Must include a worked example for aws-postgres."""
        self.assertIn("aws-postgres", SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_covers_aws_google_sheets(self) -> None:
        """Must include a worked example for aws-google-sheets."""
        self.assertIn("aws-google-sheets", SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_mentions_secret_handle(self) -> None:
        """Must teach agents to read secret_handle from the descriptor."""
        self.assertIn("secret_handle", SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_has_flat_recipe_steps(self) -> None:
        """Must be a flat numbered recipe (at least 5 steps)."""
        import re
        steps = re.findall(r"^\s*\d+\.", SECRET_CONNECTION_RULES, re.MULTILINE)
        self.assertGreaterEqual(len(steps), 5, "Expected at least 5 numbered steps in the recipe")

    def test_secret_connection_rules_in_elicit_context(self) -> None:
        result = elicit_context()
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(result["secret_connection_rules"], SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_in_map_connections_context(self) -> None:
        result = map_connections_context()
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(result["secret_connection_rules"], SECRET_CONNECTION_RULES)

    def test_secret_connection_rules_in_generate_brd_context(self) -> None:
        result = generate_brd_context()
        self.assertIn("secret_connection_rules", result)
        self.assertEqual(result["secret_connection_rules"], SECRET_CONNECTION_RULES)

    def test_connection_descriptor_note_includes_aws_postgres(self) -> None:
        """connection_descriptor_note must include aws-postgres example."""
        from brain_ds.mcp.grounding import NODE_WRITE_TEMPLATES
        note = NODE_WRITE_TEMPLATES["Data Source"]["connection_descriptor_note"]
        self.assertIn("aws-postgres", note)

    def test_connection_descriptor_note_includes_aws_google_sheets(self) -> None:
        """connection_descriptor_note must include aws-google-sheets example."""
        from brain_ds.mcp.grounding import NODE_WRITE_TEMPLATES
        note = NODE_WRITE_TEMPLATES["Data Source"]["connection_descriptor_note"]
        self.assertIn("aws-google-sheets", note)

    def test_connection_descriptor_note_no_obsolete_google_sheets_sentence(self) -> None:
        """Obsolete 'Google Sheets delegated to agent layer / export to CSV' text must be removed."""
        from brain_ds.mcp.grounding import NODE_WRITE_TEMPLATES
        note = NODE_WRITE_TEMPLATES["Data Source"]["connection_descriptor_note"]
        self.assertNotIn("delegated to the agent layer", note)
        self.assertNotIn("export to CSV", note)


if __name__ == "__main__":
    unittest.main()
