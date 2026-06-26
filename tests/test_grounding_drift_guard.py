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

import ast
import inspect
import re
import unittest
from pathlib import Path
from typing import Any, cast

from brain_ds.mcp import grounding
from brain_ds.ontology.entity_types import EntityType
from brain_ds.scoring import similarity
from brain_ds.store.models import NodeRow


REPO_ROOT = Path(__file__).resolve().parents[1]

# EntityTypes that intentionally have NO elicitation question bank entry.
# Adding a new EntityType that should be elicited means adding it to
# QUESTION_BANK; adding one that should not means listing it here. Either way
# the choice is explicit and reviewed.
ELICIT_EXEMPT_TYPES: frozenset[str] = frozenset(
    {
        "Project",  # captured via map/brd synthesis, not the elicit interview
        "Risk",  # derived during mapping, not directly elicited
        "DataContainer",  # Data Source-internal structural node, not elicited directly
        "DataField",  # Data Source-internal structural node, not elicited directly
        "Unknown",  # fallback bucket, never elicited
    }
)


def _entity_values() -> set[str]:
    return {e.value for e in EntityType}


def _discover_category2_constants() -> set[str]:
    tree = ast.parse(inspect.getsource(grounding))
    discovered: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        else:
            continue
        for target in targets:
            if re.match(r"^[A-Z][A-Z0-9_]+$", target):
                value = getattr(grounding, target, None)
                if isinstance(value, (dict, list)):
                    discovered.add(target)
    return discovered


CATEGORY2_EXEMPT: frozenset[str] = frozenset(
    {
        "BRD_SECTION_ORDER",  # Section labels only, no entity-type references.
        "BRD_STRICT_MODE",  # Strict-mode flow prose, not entity taxonomy.
        "COMPLETENESS_GATE",  # Gate behavior prose, no literal EntityType values.
        "DELEGATION_PROTOCOL",  # Orchestration contract, not graph entity naming.
        "ELICIT_WORKFLOW",  # Interview workflow prose, no entity-name payload.
        "MAP_RAG_WORKFLOW",  # Retrieval workflow prose, no entity-name payload.
        "ORG_SLUG_RULES",  # Slug normalization rules only.
        "WORKSPACE_PROTOCOL",  # Workspace scoping contract, not ontology names.
    }
)


def _iter_string_entries(value: Any, path: str = "$") -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if isinstance(value, str):
        entries.append((path, value))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            entries.extend(_iter_string_entries(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            entries.extend(_iter_string_entries(item, f"{path}.{key}"))
    return entries


SAFE_ENTITYISH_TOKENS: frozenset[str] = frozenset(
    {
        "CsvConnector",
        "EntityType",
        "GraphQL",
        "NoSQL",
        "Obsidian",
        "RelationshipType",
    }
)


def _sweep_constant(name: str, value: Any) -> list[dict[str, str]]:
    real_entity_values = _entity_values()
    drift: list[dict[str, str]] = []
    for path, text in _iter_string_entries(value):
        for token in sorted(set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))):
            if token not in real_entity_values and token not in SAFE_ENTITYISH_TOKENS:
                drift.append({"constant": name, "path": path, "token": token})
    return drift


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

    def test_every_category2_constant_is_classified(self) -> None:
        discovered = _discover_category2_constants()
        swept = {name for name in discovered if name not in CATEGORY2_EXEMPT}
        missing = discovered - swept - set(CATEGORY2_EXEMPT)
        self.assertEqual(
            missing,
            set(),
            (
                "Unclassified Category-2 constants: "
                f"{sorted(missing)}. Add each constant to the reflection sweep or to "
                "CATEGORY2_EXEMPT with a rationale."
            ),
        )

    def test_swept_category2_constants_have_no_drift_tokens(self) -> None:
        drift: list[dict[str, str]] = []
        for name in sorted(_discover_category2_constants() - set(CATEGORY2_EXEMPT)):
            drift.extend(_sweep_constant(name, getattr(grounding, name)))
        self.assertEqual(drift, [], f"Category-2 drift detected: {drift}")

    # T1a-10: PIPELINE_STAGES is discovered by drift guard and NOT exempt
    def test_pipeline_stages_discovered_and_not_exempt(self) -> None:
        discovered = _discover_category2_constants()
        self.assertIn(
            "PIPELINE_STAGES",
            discovered,
            "PIPELINE_STAGES must be auto-discovered by the drift guard sweep",
        )
        self.assertNotIn(
            "PIPELINE_STAGES",
            CATEGORY2_EXEMPT,
            "PIPELINE_STAGES must NOT be in CATEGORY2_EXEMPT — it must sweep clean",
        )

    # E-T9: SOURCE_CHANGE_DETECTION_CONTRACT is discovered, NOT exempt, sweeps clean.
    def test_source_change_detection_contract_discovered_and_not_exempt(self) -> None:
        discovered = _discover_category2_constants()
        self.assertIn(
            "SOURCE_CHANGE_DETECTION_CONTRACT",
            discovered,
            "SOURCE_CHANGE_DETECTION_CONTRACT must be auto-discovered by the drift guard sweep",
        )
        self.assertNotIn(
            "SOURCE_CHANGE_DETECTION_CONTRACT",
            CATEGORY2_EXEMPT,
            "SOURCE_CHANGE_DETECTION_CONTRACT must NOT be in CATEGORY2_EXEMPT — it must sweep clean",
        )

    def test_source_change_detection_contract_sweeps_clean(self) -> None:
        drift = _sweep_constant(
            "SOURCE_CHANGE_DETECTION_CONTRACT",
            grounding.SOURCE_CHANGE_DETECTION_CONTRACT,
        )
        self.assertEqual(drift, [], f"SOURCE_CHANGE_DETECTION_CONTRACT drift: {drift}")

    def test_source_change_detection_contract_documents_verdicts_and_baseline(self) -> None:
        contract = grounding.SOURCE_CHANGE_DETECTION_CONTRACT
        verdicts = contract["verdicts"]
        for v in ("new", "unchanged", "changed", "unknown-baseline"):
            self.assertIn(v, verdicts)
        baseline_fields = contract["baseline_fields"]
        for f in ("schema_hash", "documented_schema_snapshot", "last_documented_at"):
            self.assertIn(f, baseline_fields)
        delta_shape = contract["delta_shape"]
        for k in ("added_columns", "removed_columns", "altered_columns", "added_tables", "removed_tables"):
            self.assertIn(k, delta_shape)
        # governance stance present (auditable decision, never silent overwrite)
        self.assertIn("governance", contract)

    # T1-5/T1-6: ARTIFACT_CONTRACT is discovered by drift guard and NOT exempt
    def test_artifact_contract_discovered_and_not_exempt(self) -> None:
        discovered = _discover_category2_constants()
        self.assertIn(
            "ARTIFACT_CONTRACT",
            discovered,
            "ARTIFACT_CONTRACT must be auto-discovered by the drift guard sweep",
        )
        self.assertNotIn(
            "ARTIFACT_CONTRACT",
            CATEGORY2_EXEMPT,
            "ARTIFACT_CONTRACT must NOT be in CATEGORY2_EXEMPT — it must sweep clean",
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


class GroundingCategory2SweepTests(unittest.TestCase):
    def test_sweep_catches_stale_entity_name(self) -> None:
        drift = _sweep_constant("TEST_CONSTANT", {"nested": ["StaleEntity"]})
        self.assertEqual(
            drift,
            [{"constant": "TEST_CONSTANT", "path": "$.nested[0]", "token": "StaleEntity"}],
        )


class GroundingPipelineContractTests(unittest.TestCase):
    def test_deliverable_contract_sections_fixed_and_ordered(self) -> None:
        contract = grounding.DELIVERABLE_CONTRACT
        self.assertEqual(
            contract["sections"],
            (
                "outcome_title",
                "quick_path",
                "details_table",
                "checklist",
                "next_step",
            ),
        )

    def test_deliverable_contract_scoped_to_pipeline_artifacts(self) -> None:
        contract = grounding.DELIVERABLE_CONTRACT
        self.assertEqual(
            contract["applies_to"],
            ("recon", "plan", "source-docs", "consolidation", "dry-run"),
        )
        self.assertNotIn("brd", contract["applies_to"])
        self.assertNotIn("map", contract["applies_to"])

    def test_deliverable_contract_injected_only_into_pipeline_composers(self) -> None:
        elicit_ctx = grounding.elicit_context()
        self.assertIn("deliverable_contract", elicit_ctx)
        self.assertEqual(elicit_ctx["deliverable_contract"], grounding.DELIVERABLE_CONTRACT)

        brd_ctx = grounding.generate_brd_context()
        self.assertNotIn("deliverable_contract", brd_ctx)

        map_ctx = grounding.map_connections_context()
        self.assertNotIn("deliverable_contract", map_ctx)

    def test_brd_and_map_contracts_untouched(self) -> None:
        self.assertEqual(len(grounding.BRD_SECTION_ORDER), 14)
        self.assertEqual(
            grounding.BRD_GRAPH_PERSISTENCE_CONTRACT["update_node_template"]["card_sections"][0]["title"],
            "Contenido",
        )
        self.assertGreaterEqual(len(grounding.CONNECTION_RULES["rules"]), 7)

    def test_handoff_summary_is_optional_and_additive(self) -> None:
        self.assertNotIn("handoff_summary", grounding.ARTIFACT_CONTRACT["source-docs"]["required_keys"])
        self.assertNotIn("handoff_summary", grounding.ARTIFACT_CONTRACT["map"]["required_keys"])
        self.assertNotIn("handoff_summary", grounding.ARTIFACT_CONTRACT["brd"]["required_keys"])

    def test_deliverable_contract_sweeps_clean(self) -> None:
        self.assertNotIn("DELIVERABLE_CONTRACT", CATEGORY2_EXEMPT)
        drift = _sweep_constant("DELIVERABLE_CONTRACT", grounding.DELIVERABLE_CONTRACT)
        self.assertEqual(drift, [])

    def test_delegation_protocol_has_dry_run(self) -> None:
        protocol = grounding.DELEGATION_PROTOCOL
        self.assertIn("dry_run", protocol)
        dry_run = protocol["dry_run"]
        self.assertIn("trigger_phrase", dry_run)
        self.assertIn("steps", dry_run)
        self.assertIn("no_graph_writes_guard", dry_run)

    def test_currency_elicitation_workflow_documents_modes_and_pending_deferral(self) -> None:
        workflow = grounding.ELICIT_WORKFLOW
        currency = workflow["currency_elicitation"]
        self.assertEqual(currency["agent"], "brainds-currency-elicitor")
        self.assertEqual(currency["modes"], ("open", "scoped"))
        steps = " ".join(currency["steps"])
        for token in ("assess_currency", "retrieve_context", "insert_pending_question", "pending"):
            with self.subTest(token=token):
                self.assertIn(token, steps)

    def test_delegation_protocol_registers_currency_elicitor(self) -> None:
        protocol = grounding.DELEGATION_PROTOCOL
        registered = protocol["registered_subagents"]
        self.assertIn("brainds-currency-elicitor", registered)
        self.assertIn("assess_currency", registered["brainds-currency-elicitor"]["tools"])
        self.assertIn("insert_pending_question", registered["brainds-currency-elicitor"]["tools"])
        self.assertIn("retrieve_context", registered["brainds-currency-elicitor"]["tools"])

    def test_source_docs_artifact_contract_has_slice_fields(self) -> None:
        source_docs = grounding.ARTIFACT_CONTRACT["source-docs"]
        self.assertIn("slice_id", source_docs["required_keys"])
        self.assertIn("assigned_objects", source_docs["required_keys"])

    def test_source_docs_artifact_contract_has_coverage_status(self) -> None:
        source_docs = grounding.ARTIFACT_CONTRACT["source-docs"]
        self.assertEqual(source_docs["coverage_status_values"], ("documented", "skipped"))
        self.assertIn("type_fields_notes", source_docs)
        self.assertIn("skip_reason_notes", source_docs)

    def test_source_docs_artifact_contract_lists_source_types(self) -> None:
        source_docs = grounding.ARTIFACT_CONTRACT["source-docs"]
        self.assertEqual(
            source_docs["source_type_values"],
            grounding.RECON_SOURCE_TYPES["supported"] + grounding.RECON_SOURCE_TYPES["unsupported"],
        )

    def test_source_docs_artifact_contract_sweeps_clean(self) -> None:
        self.assertNotIn("ARTIFACT_CONTRACT", CATEGORY2_EXEMPT)
        drift = _sweep_constant("ARTIFACT_CONTRACT", grounding.ARTIFACT_CONTRACT)
        self.assertEqual(drift, [])

    def test_recon_source_types_cover_supported_and_unsupported(self) -> None:
        source_types = grounding.RECON_SOURCE_TYPES
        self.assertIn("sqlite", source_types["supported"])
        self.assertIn("google-sheets", source_types["supported"])
        self.assertIn("unsupported-json-api", source_types["unsupported"])
        self.assertIn("unsupported-unstructured", source_types["unsupported"])

    def test_unsupported_source_requires_recommended_next(self) -> None:
        self.assertEqual(grounding.UNSUPPORTED_RECOMMENDED_NEXT, "manual contract required")

    def test_recon_source_types_sweep_clean(self) -> None:
        drift = _sweep_constant("RECON_SOURCE_TYPES", grounding.RECON_SOURCE_TYPES)
        self.assertEqual(drift, [])

    # DDS-7: SOURCE_DOCUMENTATION_BUNDLE_CONTRACT is discovered, NOT exempt, sweeps clean.
    def test_source_documentation_bundle_contract_discovered_and_not_exempt(self) -> None:
        discovered = _discover_category2_constants()
        self.assertIn(
            "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT",
            discovered,
            "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT must be auto-discovered by the drift guard sweep",
        )
        self.assertNotIn(
            "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT",
            CATEGORY2_EXEMPT,
            "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT must NOT be in CATEGORY2_EXEMPT — it must sweep clean",
        )

    def test_source_documentation_bundle_contract_sweeps_clean(self) -> None:
        drift = _sweep_constant(
            "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT",
            grounding.SOURCE_DOCUMENTATION_BUNDLE_CONTRACT,
        )
        self.assertEqual(drift, [], f"SOURCE_DOCUMENTATION_BUNDLE_CONTRACT drift: {drift}")

    def test_source_exploration_flow_has_four_substeps(self) -> None:
        steps = grounding.DELEGATION_PROTOCOL["source_exploration_flow"]
        self.assertEqual(len(steps), 4)
        joined = " ".join(steps)
        for token in ("recon", "plan", "document", "consolidate"):
            self.assertIn(token, joined)

    def test_artifact_phases_include_recon_and_plan(self) -> None:
        phases = grounding.DELEGATION_PROTOCOL["artifact_keys"]["phases"]
        self.assertIn("recon", phases)
        self.assertIn("plan", phases)

    def test_unsupported_objects_in_plan_as_skip(self) -> None:
        joined = " ".join(grounding.DELEGATION_PROTOCOL["source_exploration_flow"])
        self.assertIn("unsupported", joined)
        self.assertIn("skip", joined)


class GroundingPipelineMirrorParityTests(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        path = REPO_ROOT / relative_path
        if not path.exists() and relative_path.startswith(".claude/agents/"):
            self.skipTest(f"agent prose file absent ({path.name}) — installed per-client artifact, mirror not verified here")
        return path.read_text(encoding="utf-8")

    def _assert_tokens(self, content: str, *, must_have: tuple[str, ...], must_not_have: tuple[str, ...] = ()) -> None:
        for token in must_have:
            with self.subTest(token=token):
                self.assertIn(token, content)
        for token in must_not_have:
            with self.subTest(forbidden=token):
                self.assertNotIn(token, content)

    def test_source_explorer_agent_and_prompt_reference_pipeline_deliverable_contract(self) -> None:
        must_have = (
            "DELIVERABLE_CONTRACT",
            "Outcome title",
            "Quick path / summary",
            "Details table",
            "Coverage checklist",
            "Next step",
            "plain canonical headings only",
            "no numbering",
            "no extra H2 sections",
            "canonical-payload",
            "artifact_type",
            "source-docs",
            "recon",
            "plan",
            "dry-run",
        )
        for relative_path in (
            ".claude/agents/brainds-source-explorer.md",
            "prompts/brainds-source-explorer.md",
        ):
            with self.subTest(path=relative_path):
                self._assert_tokens(self._read(relative_path), must_have=must_have)

    def test_graph_mapper_agent_and_prompt_reference_pipeline_deliverable_contract(self) -> None:
        must_have = (
            "DELIVERABLE_CONTRACT",
            "Outcome title",
            "Quick path / summary",
            "Details table",
            "Coverage checklist",
            "Next step",
            "canonical-payload",
            "artifact_type",
            "source-docs",
            "assert_deliverable_shape",
            "real validator",
            "artifact text or file",
        )
        for relative_path in (
            ".claude/agents/brainds-graph-mapper.md",
            "prompts/brainds-graph-mapper.md",
        ):
            with self.subTest(path=relative_path):
                self._assert_tokens(self._read(relative_path), must_have=must_have)

    def test_connection_mapper_and_brd_writer_only_add_optional_handoff_summary(self) -> None:
        for relative_path in (
            ".claude/agents/brainds-connection-mapper.md",
            "prompts/brainds-connection-mapper.md",
            ".claude/agents/brainds-brd-writer.md",
            "prompts/brainds-brd-writer.md",
        ):
            with self.subTest(path=relative_path):
                content = self._read(relative_path)
                self._assert_tokens(content, must_have=("handoff_summary", "optional", "additive"), must_not_have=("DELIVERABLE_CONTRACT",))

    def test_connection_mapper_agent_and_prompt_reference_calibration_decision_tree(self) -> None:
        must_have = (
            "calibration",
            "advisory_only",
            "rollout_ready",
            "calibration_verdict",
            "advisory_accept",
            "advisory_abstain",
            "advisory_reject",
            "score >= 0.5",
            "informational",
            "deferred list",
        )
        for relative_path in (
            ".claude/agents/brainds-connection-mapper.md",
            "prompts/brainds-connection-mapper.md",
        ):
            with self.subTest(path=relative_path):
                self._assert_tokens(self._read(relative_path), must_have=must_have)

    def test_orchestrator_agent_and_prompt_reference_dry_run_recipe(self) -> None:
        must_have = (
            "dry_run",
            "no_graph_writes_guard",
            "assess_completeness",
            "skip — unsupported source type",
            "union(plan slices) == recon inventory",
            "source-docs/{source-id}/recon",
            "source-docs/{source-id}/plan",
            "source-docs/{source-id}/dry-run",
        )
        for relative_path in (
            ".claude/agents/brainds-orchestrator.md",
            "prompts/brain-ds-orchestrator.md",
        ):
            with self.subTest(path=relative_path):
                self._assert_tokens(self._read(relative_path), must_have=must_have)

    def test_skill_mirror_is_byte_identical_when_present(self) -> None:
        canonical_root = REPO_ROOT / "skills"
        mirror_root = REPO_ROOT / ".opencode" / "skills"
        if not canonical_root.is_dir() or not mirror_root.is_dir():
            self.skipTest("skills mirror not present in this workspace")

        canonical_files = sorted(canonical_root.glob("*/SKILL.md"))
        mirror_files = sorted(mirror_root.glob("*/SKILL.md"))
        self.assertEqual(
            [path.parent.name for path in canonical_files],
            [path.parent.name for path in mirror_files],
            "skills/ and .opencode/skills/ must expose the same skill set",
        )
        for canonical_file in canonical_files:
            mirror_file = mirror_root / canonical_file.parent.name / "SKILL.md"
            with self.subTest(skill=canonical_file.parent.name):
                self.assertTrue(mirror_file.is_file(), f"Missing mirror for {canonical_file.parent.name}")
                self.assertEqual(
                    canonical_file.read_bytes(),
                    mirror_file.read_bytes(),
                    f"{canonical_file.parent.name} SKILL.md must be byte-identical in .opencode/skills/",
                )

    def test_data_source_internal_types_are_mirrored_in_skill_prose(self) -> None:
        expected_by_path = {
            "skills/elicit-context/SKILL.md": (
                "DataContainer",
                "DataField",
                "Data Source-internal structural nodes",
            ),
            "skills/brainds-docs/SKILL.md": (
                "| DataContainer | Overview, Structure, Fields, Purpose |",
                "| DataField | Overview, Data Type, Meaning, Quality |",
            ),
            "skills/map-connections/SKILL.md": (
                "DataContainer",
                "DataField",
                "Data Source-internal",
                "not standalone domain entities",
            ),
            "skills/brainds-registry/SKILL.md": (
                "DataContainer",
                "DataField",
                "Data Source-internal",
            ),
            "skills/SHARED_CONTEXT.md": (
                "DataContainer",
                "DataField",
            ),
            ".atl/skill-registry.md": (
                "DataContainer",
                "DataField",
                "Data Source-internal",
            ),
        }
        for relative_path, must_have in expected_by_path.items():
            with self.subTest(path=relative_path):
                self._assert_tokens(self._read(relative_path), must_have=must_have)


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

    def test_data_internal_types_are_not_assessed_for_brd_completeness(self) -> None:
        from brain_ds.mcp.completeness import ASSESSED_TYPES, assess_graph_completeness

        self.assertNotIn("DataContainer", ASSESSED_TYPES)
        self.assertNotIn("DataField", ASSESSED_TYPES)

        nodes = [_node("DS-1", "Warehouse", "Data Source")]
        result = assess_graph_completeness(nodes)
        self.assertNotIn("DataContainer", result["missing_for_brd"])
        self.assertNotIn("DataField", result["missing_for_brd"])


class ToolCountSyncTests(unittest.TestCase):
    """TOOL_REGISTRY must have exactly 32 tools after get_kpi_dossier is added."""

    def test_tool_registry_has_32_tools_after_get_kpi_dossier_added(self) -> None:
        from brain_ds.harness_check import EXPECTED_MCP_TOOL_COUNT
        from brain_ds.mcp.tools import TOOL_REGISTRY

        self.assertEqual(
            len(TOOL_REGISTRY),
            EXPECTED_MCP_TOOL_COUNT,
            f"Expected {EXPECTED_MCP_TOOL_COUNT} MCP tools, got {len(TOOL_REGISTRY)}. "
            "KPI composition dossier PR1 must add get_kpi_dossier.",
        )
        self.assertIn(
            "assess_currency",
            TOOL_REGISTRY,
            "assess_currency must be registered in TOOL_REGISTRY (Brick E PR2).",
        )
        self.assertIn(
            "insert_pending_question",
            TOOL_REGISTRY,
            "insert_pending_question must be registered in TOOL_REGISTRY for Brick E pending deferral.",
        )
        self.assertIn(
            "manage_clusters",
            TOOL_REGISTRY,
            "manage_clusters must be registered for semantic cluster governance.",
        )
        self.assertIn(
            "get_kpi_dossier",
            TOOL_REGISTRY,
            "get_kpi_dossier must be registered for KPI dossier composition.",
        )


if __name__ == "__main__":
    unittest.main()
