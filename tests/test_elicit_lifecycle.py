from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from brain_ds.verify.elicit_compliance import PHASE_PATTERN, check_elicit_compliance


REPO_ROOT = Path(__file__).resolve().parents[1]
ELICIT_DIR = REPO_ROOT / ".elicit"
ALLOWED_PHASES = (
    "elicit",
    "source-exploration",
    "source-docs",
    "map",
    "brd",
    "verify",
    "archive",
)
KNOWN_AGENTS = {
    "brainds-orchestrator",
    "brainds-source-explorer",
    "brainds-query-consultant",
    "brainds-graph-mapper",
    "brainds-connection-mapper",
    "brainds-brd-writer",
}
REQUIRED_PROTOCOL_KEYS = (
    "role",
    "session_setup",
    "artifact_keys",
    "handoff_rule",
    "source_exploration_flow",
    "skill_scope",
    "pipeline_stages",
    "intake_paths",
)
REQUIRED_AGENTS = tuple(KNOWN_AGENTS)
# C-6: canonical PHASE_PATTERN imported from brain_ds.verify.elicit_compliance above
ELICIT_NAME_PATTERN = PHASE_PATTERN  # alias — same object, no local duplicate


class TestElicitLifecycle(unittest.TestCase):
    def _read_optional_client_artifact(self, relative_path: str) -> str:
        artifact = REPO_ROOT / relative_path
        if not artifact.exists():
            self.skipTest(f"client artifact absent ({artifact.name}) — installed per-client artifact, mirror not verified here")
        return artifact.read_text(encoding="utf-8")

    def test_elicit_naming_pattern(self) -> None:
        files = sorted(path for path in ELICIT_DIR.glob("*.md") if path.name != "README.md")

        for file_path in files:
            self.assertRegex(
                file_path.name,
                ELICIT_NAME_PATTERN,
                msg=f"Offending .elicit artifact filename: {file_path.name}",
            )

    def test_lifecycle_doc_ownership_table_consistent(self) -> None:
        lifecycle_doc = (ELICIT_DIR / "README.md").read_text(encoding="utf-8")

        for phase in ALLOWED_PHASES:
            self.assertIn(f"`{phase}`", lifecycle_doc)

        for agent in (
            "brainds-orchestrator",
            "brainds-source-explorer",
            "brainds-connection-mapper",
            "brainds-brd-writer",
        ):
            self.assertIn(agent, lifecycle_doc)

        owners = re.findall(r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", lifecycle_doc)
        phase_to_owner = {phase: owner for phase, owner in owners if phase in ALLOWED_PHASES}
        self.assertEqual(set(phase_to_owner.keys()), set(ALLOWED_PHASES))

        for phase, owner in phase_to_owner.items():
            self.assertIn(owner, KNOWN_AGENTS, msg=f"Unknown owner '{owner}' for phase '{phase}'")

    def test_sdd_flow_doc_references_delegation_protocol_constants(self) -> None:
        flow_doc = (REPO_ROOT / "docs" / "SDD_FLOW.md").read_text(encoding="utf-8")

        for key in REQUIRED_PROTOCOL_KEYS:
            self.assertIn(key, flow_doc)

    def test_skill_registry_lists_all_resolvable_agents(self) -> None:
        registry_doc = (REPO_ROOT / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
        agents_section = registry_doc.split("## Agents", maxsplit=1)[1]
        registered = set(re.findall(r"^\|\s*`([^`]+)`\s*\|", agents_section, flags=re.MULTILINE))
        definitions = {path.stem for path in (REPO_ROOT / ".claude" / "agents").glob("*.md")}

        self.assertEqual(registered, definitions)

    def test_skill_registry_has_an_agents_section_for_lifecycle_entries(self) -> None:
        registry_doc = (REPO_ROOT / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
        self.assertIn("## Agents", registry_doc)

        agents_section = registry_doc.split("## Agents", maxsplit=1)[1]
        paths = re.findall(r"\|\s*`(\.claude/agents/[^`]+\.md)`\s*\|", agents_section)
        self.assertTrue(paths)
        for relative_path in paths:
            with self.subTest(path=relative_path):
                self.assertTrue((REPO_ROOT / relative_path).is_file())

    # T1a-1: PIPELINE_STAGES constant shape and order
    def test_pipeline_stages_constant_shape_and_order(self) -> None:
        from brain_ds.mcp import grounding

        stages = grounding.PIPELINE_STAGES
        self.assertIsInstance(stages, list)
        self.assertEqual(len(stages), 6)

        expected_order = ["setup", "intake", "map", "brd", "verify", "archive"]
        actual_order = [s["stage"] for s in stages]
        self.assertEqual(actual_order, expected_order)

        for stage in stages:
            self.assertIn("stage", stage)
            self.assertIn("description", stage)
            self.assertIn("agents", stage)

        intake = stages[1]
        self.assertEqual(intake["stage"], "intake")
        self.assertIn("intake_paths", intake)
        intake_paths = intake["intake_paths"]
        self.assertIn("datasource", intake_paths)
        self.assertIn("human_org", intake_paths)

    # T1a-3: pipeline_stages exposed in all 3 grounding payloads
    def test_pipeline_stages_in_all_three_grounding_payloads(self) -> None:
        from brain_ds.mcp import grounding

        elicit = grounding.elicit_context()
        self.assertIn("pipeline_stages", elicit)
        self.assertEqual(elicit["pipeline_stages"], grounding.PIPELINE_STAGES)
        self.assertIn("intake_paths", elicit)
        self.assertEqual(elicit["intake_paths"], grounding.PIPELINE_STAGES[1]["intake_paths"])

        map_ctx = grounding.map_connections_context()
        self.assertIn("pipeline_stages", map_ctx)
        self.assertEqual(map_ctx["pipeline_stages"], grounding.PIPELINE_STAGES)

        brd_ctx = grounding.generate_brd_context()
        self.assertIn("pipeline_stages", brd_ctx)
        self.assertEqual(brd_ctx["pipeline_stages"], grounding.PIPELINE_STAGES)

    # T1a-8: verify gate writes artifact and blocks archive on CRITICAL
    def test_verify_artifact_clean_passes_compliance(self) -> None:
        import tempfile
        import json
        from brain_ds.verify.elicit_compliance import check_elicit_compliance

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            verify_file = tmp_path / "verify-acme-2026-06-14.md"
            envelope = {
                "artifact_type": "verify",
                "graph_id": "acme",
                "stage": "verify",
                "status": "PASS",
                "critical_count": 0,
                "findings": [],
                "gate": "PASS",
            }
            verify_file.write_text(
                f"# Verify\n\n```json\n{json.dumps(envelope, indent=2)}\n```\n",
                encoding="utf-8",
            )
            findings = check_elicit_compliance(tmp_path)
            critical = [f for f in findings if f.severity == "CRITICAL"]
            self.assertEqual(critical, [], f"Expected no CRITICAL for clean verify artifact, got: {critical}")

    # T1-17/T1-18: agent prose canonical-payload instruction
    def test_source_explorer_claude_agent_mentions_canonical_payload(self) -> None:
        content = self._read_optional_client_artifact(".claude/agents/brainds-source-explorer.md")
        self.assertIn("canonical-payload", content, "brainds-source-explorer.md must mention canonical-payload")
        self.assertIn("artifact_type", content, "brainds-source-explorer.md must mention artifact_type")

    def test_source_explorer_prompt_mentions_canonical_payload(self) -> None:
        prompt_file = REPO_ROOT / "prompts" / "brainds-source-explorer.md"
        content = prompt_file.read_text(encoding="utf-8")
        self.assertIn("canonical-payload", content, "brainds-source-explorer prompt must mention canonical-payload")
        self.assertIn("artifact_type", content, "brainds-source-explorer prompt must mention artifact_type")

    def test_brd_writer_claude_agent_mentions_canonical_payload(self) -> None:
        content = self._read_optional_client_artifact(".claude/agents/brainds-brd-writer.md")
        self.assertIn("canonical-payload", content, "brainds-brd-writer.md must mention canonical-payload")
        self.assertIn("artifact_type", content, "brainds-brd-writer.md must mention artifact_type")

    def test_brd_writer_prompt_mentions_canonical_payload(self) -> None:
        prompt_file = REPO_ROOT / "prompts" / "brainds-brd-writer.md"
        content = prompt_file.read_text(encoding="utf-8")
        self.assertIn("canonical-payload", content, "brainds-brd-writer prompt must mention canonical-payload")
        self.assertIn("artifact_type", content, "brainds-brd-writer prompt must mention artifact_type")

    def test_connection_mapper_claude_agent_mentions_canonical_payload(self) -> None:
        content = self._read_optional_client_artifact(".claude/agents/brainds-connection-mapper.md")
        self.assertIn("canonical-payload", content, "brainds-connection-mapper.md must mention canonical-payload")
        self.assertIn("artifact_type", content, "brainds-connection-mapper.md must mention artifact_type")

    # T1-13/T1-14: connection-mapper Write tool grant
    def test_connection_mapper_claude_agent_has_write_tool(self) -> None:
        content = self._read_optional_client_artifact(".claude/agents/brainds-connection-mapper.md")
        self.assertIn("- Write", content, "brainds-connection-mapper.md must list Write in its tools")

    def test_connection_mapper_prompt_mentions_elicit_artifact_write(self) -> None:
        prompt_file = REPO_ROOT / "prompts" / "brainds-connection-mapper.md"
        content = prompt_file.read_text(encoding="utf-8")
        self.assertIn(".elicit", content, "brainds-connection-mapper prompt must mention .elicit")
        self.assertIn("map-", content, "brainds-connection-mapper prompt must mention map- artifact")

    # C-1: artifact in subdir is discovered
    def test_subdir_artifact_is_discovered(self) -> None:
        """Phase-named .md in elicit_dir/<subdir>/ must be found by check_elicit_compliance."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subdir = tmp_path / "my-change"
            subdir.mkdir(parents=True)
            brd_file = subdir / "brd-my-change-2026-06-14.md"
            graph_id = "my-change"
            payload = {
                "artifact_type": "brd",
                "graph_id": graph_id,
                "brd_node": {
                    "node_id": f"brd-{graph_id}",
                    "label": "BRD",
                    "type": "Unknown",
                    "card_sections": [
                        {"title": "Contenido", "content": "some content", "icon": "", "order": 0}
                    ],
                },
                "markdown": "Content with [[wikilink]]",
                "completeness_gate": {"pre_mapping_recommendation": "proceed_with_gaps"},
            }
            brd_file.write_text(
                f"# BRD\n\n```json\n{json.dumps(payload, indent=2)}\n```\n",
                encoding="utf-8",
            )
            findings = check_elicit_compliance(tmp_path)
            critical = [f for f in findings if f.severity == "CRITICAL"]
            self.assertEqual(
                critical,
                [],
                f"Subdir artifact should be discovered with no CRITICAL; got: {critical}",
            )

    # C-2: README in subdir is silently ignored
    def test_readme_in_subdir_is_ignored(self) -> None:
        """README.md in a subdir must produce zero findings."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subdir = tmp_path / "my-change"
            subdir.mkdir(parents=True)
            readme = subdir / "README.md"
            readme.write_text("# Lifecycle docs\n\nNo JSON payload here.", encoding="utf-8")
            findings = check_elicit_compliance(tmp_path)
            readme_findings = [f for f in findings if f.file.name == "README.md"]
            self.assertEqual(
                readme_findings,
                [],
                "README.md in subdir must be silently ignored",
            )

    # C-3: phase-named but broken artifact in subdir → CRITICAL
    def test_broken_subdir_artifact_raises_critical(self) -> None:
        """Phase-named file in subdir with no JSON payload must raise CRITICAL."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subdir = tmp_path / "my-change"
            subdir.mkdir(parents=True)
            broken = subdir / "map-my-change-2026-06-14.md"
            broken.write_text("# Map\n\nSome prose but no JSON payload.", encoding="utf-8")
            findings = check_elicit_compliance(tmp_path)
            critical = [f for f in findings if f.severity == "CRITICAL" and f.file == broken]
            self.assertGreater(
                len(critical),
                0,
                "phase-named file in subdir with missing payload must raise CRITICAL",
            )

    # C-4: flat artifacts still discovered (backward compat)
    def test_flat_artifact_backward_compat(self) -> None:
        """Flat .elicit/*.md artifacts must still be discovered after the glob change."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            flat = tmp_path / "elicit-my-project-2026-06-14.md"
            payload = {
                "artifact_type": "elicit",
                "completeness_gate": {"pre_mapping_recommendation": "proceed_with_gaps"},
            }
            flat.write_text(
                f"# Elicit\n\n```json\n{json.dumps(payload, indent=2)}\n```\n",
                encoding="utf-8",
            )
            findings = check_elicit_compliance(tmp_path)
            critical = [f for f in findings if f.severity == "CRITICAL"]
            self.assertEqual(
                critical,
                [],
                f"Flat artifact must still be found and valid; got CRITICAL: {critical}",
            )

    def test_verify_artifact_blocked_gate_raises_critical(self) -> None:
        import tempfile
        import json
        from brain_ds.verify.elicit_compliance import check_elicit_compliance

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            verify_file = tmp_path / "verify-acme-2026-06-14.md"
            envelope = {
                "graph_id": "acme",
                "stage": "verify",
                "status": "FAIL",
                "critical_count": 1,
                "findings": ["BRD node is missing wikilinks"],
                "gate": "BLOCKED",
            }
            verify_file.write_text(
                f"# Verify\n\n```json\n{json.dumps(envelope, indent=2)}\n```\n",
                encoding="utf-8",
            )
            findings = check_elicit_compliance(tmp_path)
            critical = [f for f in findings if f.severity == "CRITICAL"]
            self.assertGreater(len(critical), 0, "Expected CRITICAL finding for BLOCKED verify gate")
