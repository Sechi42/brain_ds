from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic.collect_evidence import collect_evidence
from tests.eval.blind_agentic.score_report import (
    GraphSnapshotReader,
    GoldAliasResolver,
    ScoreReportError,
    edge_labels_are_compatible,
    generate_judge_packet,
    ingest_judge_response,
    load_gold_v2,
    normalize_gold_alias,
    score_evidence,
)
from tests.eval.blind_agentic.trace_schema import (
    SessionTrace,
    TraceEvent,
    TRACE_VERSION,
    write_session_trace,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class PendingQuestionInput(TypedDict):
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str | None


class BlindAgenticScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="blind-agentic-score-")
        self._test_root = Path(self._tmp.name)
        self._previous_sdd_change = os.environ.get("BRAIN_DS_SDD_CHANGE")
        self._previous_output_root = os.environ.get("BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT")
        os.environ["BRAIN_DS_SDD_CHANGE"] = "agentic-evaluation-lab"
        os.environ["BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT"] = self._test_root.as_posix()

    def tearDown(self) -> None:
        if self._previous_sdd_change is None:
            os.environ.pop("BRAIN_DS_SDD_CHANGE", None)
        else:
            os.environ["BRAIN_DS_SDD_CHANGE"] = self._previous_sdd_change
        if self._previous_output_root is None:
            os.environ.pop("BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT", None)
        else:
            os.environ["BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT"] = self._previous_output_root
        self._tmp.cleanup()

    def test_gold_v2_loader_requires_contract_sections_and_rubric_version(self) -> None:
        gold = load_gold_v2(
            Path("tests") / "gold" / "blind_agentic" / "revops_growth" / "gold_v2.json"
        )

        self.assertEqual(gold["version"], 2)
        self.assertEqual(gold["scenario"], "revops_growth")
        self.assertEqual(gold["rubric"]["version"], "2026-06-26-pr1")
        self.assertIn("canonical_nodes", gold)
        self.assertIn("expected_edges", gold)
        self.assertIn("optional_edges", gold)
        self.assertIn("forbidden_edges", gold)
        self.assertIn("pending_question_themes", gold)

    def test_gold_v2_loader_fails_closed_when_required_data_is_missing(self) -> None:
        invalid_path = self._test_root / "invalid-gold-v2.json"
        invalid_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_path.write_text(
            json.dumps({"version": 2, "scenario": "revops_growth", "rubric": {"version": "x"}}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ScoreReportError, "canonical_nodes"):
            load_gold_v2(invalid_path)

    def test_score_report_fails_closed_when_gold_v2_is_missing(self) -> None:
        repo_root = self._test_root / "missing-gold-v2-repo"
        gold_root = repo_root / "tests" / "gold" / "blind_agentic" / "revops_growth"
        gold_root.mkdir(parents=True, exist_ok=True)
        for name in ("rubric.json", "expected_kpi_lineage.json", "gold_graph.json"):
            source = REPO_ROOT / "tests" / "gold" / "blind_agentic" / "revops_growth" / name
            (gold_root / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        evidence = self._evidence_bundle(
            "score-run-missing-gold-v2", generated_text=self._complete_generated_text()
        )

        with self.assertRaisesRegex(ScoreReportError, "gold_v2.json"):
            score_evidence(
                scenario="revops_growth",
                evidence_path=evidence,
                out_path=evidence.parent / "report.json",
                repo_root=repo_root,
            )

    def test_alias_normalization_is_gold_only_and_scoped_by_entity_type(self) -> None:
        gold = load_gold_v2(
            Path("tests") / "gold" / "blind_agentic" / "revops_growth" / "gold_v2.json"
        )
        resolver = GoldAliasResolver(gold["canonical_nodes"])

        self.assertEqual(
            normalize_gold_alias("Márketing-Campaigns__2026"), "marketing campaigns 2026"
        )
        self.assertEqual(resolver.resolve("Data Source", "MKT Campaigns"), "marketing_campaigns")
        self.assertEqual(resolver.resolve("KPI", "Net Revenue Retention"), "nrr")
        self.assertIsNone(resolver.resolve("KPI", "MKT Campaigns"))
        self.assertIsNone(resolver.resolve("Data Source", "Made Up Source"))

    def test_edge_label_compatibility_normalizes_labels_and_respects_direction(self) -> None:
        self.assertTrue(
            edge_labels_are_compatible(
                "measured-from", ["measured_from"], direction="target_to_source"
            )
        )
        self.assertTrue(
            edge_labels_are_compatible("depends on", ["depends_on"], direction="source_to_target")
        )
        self.assertFalse(
            edge_labels_are_compatible("measured_from", ["measures"], direction="source_to_target")
        )

    def test_score_report_emits_weighted_axes_and_lineage_first_total(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-001",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        axes = report["deterministic"]["axes"]
        self.assertEqual(axes["lineage"]["weight"], 0.35)
        self.assertEqual(axes["lineage"]["score_0_5"], 5)
        self.assertEqual(report["overall_score_0_5"], 5.0)
        self.assertEqual(sum(axis["weight"] for axis in axes.values()), 1.0)
        self.assertEqual(report["anti_contamination"]["status"], "passed")

    def test_score_report_records_missing_expected_lineage_from_graph_snapshot(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-002",
            generated_text="Pipeline was reviewed, but source lineage was not documented.",
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        lineage_axis = report["deterministic"]["axes"]["lineage"]
        self.assertLess(lineage_axis["score_0_5"], 5)
        self.assertIn("crm_accounts->pipeline", lineage_axis["missing_expected"])
        self.assertLess(report["overall_score_0_5"], 5.0)

    def test_score_report_uses_frozen_evidence_snapshot_for_stable_hash(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-frozen-hash",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["immutable_evidence_snapshot"] = {
            "status": "frozen",
            "algorithm": "sha256",
            "files": [
                {"path": "generated/diagnosis.md", "sha256": "a" * 64},
                {"path": "graph/store.db", "sha256": "b" * 64},
            ],
            "evidence_hash": "c" * 64,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        (evidence / "generated" / "diagnosis.md").write_text(
            "# Mutated after snapshot\n\nThis must not redefine the packet hash.", encoding="utf-8"
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["evidence_hash"], "c" * 64)

    def test_score_report_uses_collect_snapshot_hash_after_generated_file_mutates(self) -> None:
        subject = self._subject_workspace_with_graph(
            "score-run-collected-frozen-hash",
            generated_text=self._business_generated_text_without_lineage_ids(),
            include_all_expected=True,
        )
        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="score-run-collected-frozen-hash",
            subject_path=subject,
            evidence_path=subject.parent / "evidence",
            repo_root=Path.cwd(),
        )
        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        frozen_hash = manifest["immutable_evidence_snapshot"]["evidence_hash"]
        (bundle.evidence_path / "generated" / "diagnosis.md").write_text(
            "# Mutated after collection\n\nThis must not redefine packet identity.",
            encoding="utf-8",
        )
        packet_path = bundle.evidence_path.parent / "judge_packet.json"

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=bundle.evidence_path,
            out_path=bundle.evidence_path.parent / "report.json",
            repo_root=Path.cwd(),
            judge_packet_out=packet_path,
        )
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        self.assertEqual(report["evidence_hash"], frozen_hash)
        self.assertEqual(packet["evidence_hash"], frozen_hash)

    def test_judge_packet_identifies_deleted_generated_file_after_collection(self) -> None:
        subject = self._subject_workspace_with_graph(
            "score-run-deleted-generated-output",
            generated_text=self._business_generated_text_without_lineage_ids(),
            include_all_expected=True,
        )
        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="score-run-deleted-generated-output",
            subject_path=subject,
            evidence_path=subject.parent / "evidence",
            repo_root=Path.cwd(),
        )
        (bundle.evidence_path / "generated" / "diagnosis.md").unlink()

        packet = generate_judge_packet(
            scenario="revops_growth",
            evidence_path=bundle.evidence_path,
            repo_root=Path.cwd(),
        )

        self.assertEqual(packet["generated_excerpts"], [])
        self.assertEqual(packet["missing_items"]["generated_files"], ["generated/diagnosis.md"])

    def test_score_report_fails_closed_when_graph_snapshot_is_unreadable(self) -> None:
        evidence = self._evidence_bundle(
            "score-run-invalid-graph",
            generated_text=self._complete_generated_text(),
        )

        with self.assertRaisesRegex(ScoreReportError, "captured graph DB"):
            score_evidence(
                scenario="revops_growth",
                evidence_path=evidence,
                out_path=evidence.parent / "report.json",
                repo_root=Path.cwd(),
            )

    def test_graph_snapshot_reader_reads_nodes_edges_and_pending_questions(self) -> None:
        evidence = self._graph_evidence_bundle("graph-reader-run")

        snapshot = GraphSnapshotReader.from_manifest(evidence / "manifest.json").read()

        self.assertEqual(snapshot.graph_id, "revops_graph")
        self.assertEqual([node["id"] for node in snapshot.nodes], ["mkt", "pipeline"])
        self.assertEqual(snapshot.nodes[0]["label"], "MKT Campaigns")
        self.assertEqual(snapshot.edges[0]["label"], "influences")
        self.assertEqual(
            snapshot.pending_questions[0]["question_text"], "Who is the accountable source owner?"
        )

    def test_score_report_uses_graph_semantic_lineage_and_pending_theme_coverage(self) -> None:
        evidence = self._graph_evidence_bundle(
            "graph-score-run",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        deterministic = report["deterministic"]
        self.assertEqual(deterministic["axes"]["lineage"]["score_0_5"], 5)
        self.assertEqual(deterministic["axes"]["entity_source"]["score_0_5"], 5)
        self.assertEqual(deterministic["axes"]["pending_questions"]["score_0_5"], 5)
        self.assertEqual(deterministic["status"], "pass")
        self.assertIsNone(report["advisory_judge"])
        self.assertEqual(report["rubric_version"], "2026-06-26-pr1")

    def test_optional_edges_are_reported_when_present_and_neutral_when_absent(self) -> None:
        absent_evidence = self._graph_evidence_bundle(
            "graph-score-optional-absent-run",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        present_evidence = self._graph_evidence_bundle(
            "graph-score-optional-present-run",
            include_all_expected=True,
            include_optional_edge=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )

        absent_report = score_evidence(
            scenario="revops_growth",
            evidence_path=absent_evidence,
            out_path=absent_evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )
        present_report = score_evidence(
            scenario="revops_growth",
            evidence_path=present_evidence,
            out_path=present_evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        absent_lineage = absent_report["deterministic"]["axes"]["lineage"]
        present_lineage = present_report["deterministic"]["axes"]["lineage"]
        self.assertEqual(absent_lineage["score_0_5"], 5)
        self.assertEqual(present_lineage["score_0_5"], 5)
        self.assertIn("nrr->billing_subscriptions", absent_lineage["missing_optional"])
        self.assertIn("nrr->billing_subscriptions", present_lineage["matched_optional"])
        self.assertIn(
            "nrr->billing_subscriptions",
            (present_evidence.parent / "report.md").read_text(encoding="utf-8"),
        )

    def test_score_report_penalizes_forbidden_graph_edges_and_unknown_aliases(self) -> None:
        evidence = self._graph_evidence_bundle(
            "graph-score-forbidden-run",
            include_unknown_alias=True,
            include_forbidden_edge=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        lineage_axis = report["deterministic"]["axes"]["lineage"]
        entity_axis = report["deterministic"]["axes"]["entity_source"]
        self.assertLess(lineage_axis["score_0_5"], 5)
        self.assertIn("support_tickets->pipeline", lineage_axis["forbidden_matches"])
        self.assertIn("finance_revenue", entity_axis["missing_expected"])

    def test_score_report_preserves_comparable_rerun_metadata(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-003",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
            metadata={
                "model_provider": "opencode",
                "model": "manual-membership",
                "manual_deviations": ["none"],
            },
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        comparable = report["comparable_rerun_metadata"]
        self.assertEqual(comparable["prompt_version"], "revops-growth-v1")
        self.assertEqual(comparable["fixture_version"], "revops-growth-fixture-v1")
        self.assertEqual(comparable["rubric_version"], "2026-06-26-pr1")
        self.assertEqual(comparable["model_provider"], "opencode")
        self.assertEqual(comparable["manual_deviations"], ["none"])

    def test_score_report_writes_deterministic_json_and_markdown(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-004",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        out_path = evidence.parent / "report.json"

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=out_path,
            repo_root=Path.cwd(),
        )

        expected_root = REPO_ROOT / "tests" / "gold" / "blind_agentic" / "revops_growth"
        expected_json = json.loads(
            (expected_root / "expected_report_success.json").read_text(encoding="utf-8")
        )
        expected_markdown = (expected_root / "expected_report_success.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(report["axes"], expected_json["axes"])
        self.assertEqual(report["deterministic"]["axes"], expected_json["axes"])
        self.assertEqual(
            report["deterministic"]["overall_score_0_5"], expected_json["overall_score_0_5"]
        )
        self.assertEqual(report["advisory_judge"], None)
        self.assertEqual(
            json.loads(out_path.read_text(encoding="utf-8"))["deterministic"],
            report["deterministic"],
        )
        actual_markdown = re.sub(
            r"Evidence hash: `[^`]+`",
            "Evidence hash: `<dynamic>`",
            out_path.with_suffix(".md").read_text(encoding="utf-8"),
        )
        self.assertEqual(actual_markdown, expected_markdown)

    def test_judge_packet_generation_binds_evidence_hash_without_requiring_verdict(self) -> None:
        evidence = self._graph_evidence_bundle(
            "judge-packet-run",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        out_path = evidence.parent / "report.json"
        packet_path = evidence.parent / "judge_packet.json"

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=out_path,
            repo_root=Path.cwd(),
            judge_packet_out=packet_path,
        )
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        self.assertEqual(packet["packet_version"], 1)
        self.assertEqual(packet["evidence_hash"], report["evidence_hash"])
        self.assertEqual(packet["rubric_version"], report["rubric_version"])
        self.assertEqual(packet["deterministic_summary"]["status"], "pass")
        self.assertGreater(len(packet["graph_summary"]["nodes"]), 0)
        self.assertGreater(len(packet["pending_questions"]), 0)
        self.assertIsNone(report["advisory_judge"])
        self.assertEqual(
            report["judge_packet"],
            {"path": packet_path.as_posix(), "evidence_hash": report["evidence_hash"]},
        )

    def test_judge_packet_includes_generated_excerpts_and_actionable_missing_items(self) -> None:
        evidence = self._graph_evidence_bundle(
            "judge-packet-missing-items-run",
            generated_text="Pipeline was reviewed, but source lineage was not documented.",
        )

        packet = generate_judge_packet(
            scenario="revops_growth",
            evidence_path=evidence,
            repo_root=Path.cwd(),
        )

        self.assertEqual(
            packet["generated_excerpts"],
            [
                {
                    "path": "generated/diagnosis.md",
                    "excerpt": "Pipeline was reviewed, but source lineage was not documented.",
                }
            ],
        )
        self.assertIn("crm_accounts", packet["missing_items"]["canonical_nodes"])
        self.assertIn("crm_accounts->pipeline", packet["missing_items"]["lineage_edges"])
        self.assertEqual(packet["missing_items"]["artifact_classes"], [])

    def test_judge_response_ingestion_rejects_evidence_hash_mismatch(self) -> None:
        response_path = self._test_root / "mismatch-response.json"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(
            json.dumps(
                {
                    "judge_model": "manual-judge",
                    "evidence_hash": "not-the-packet-hash",
                    "verdict": "pass",
                    "axis_findings": [],
                    "disagreements": [],
                    "rationale": "Manual review agreed with deterministic scoring.",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ScoreReportError, "evidence hash"):
            ingest_judge_response(response_path, expected_evidence_hash="expected-hash")

    def test_score_report_ingests_valid_advisory_verdict_as_non_blocking_lane(self) -> None:
        evidence = self._graph_evidence_bundle(
            "judge-response-run",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        packet = generate_judge_packet(
            scenario="revops_growth",
            evidence_path=evidence,
            repo_root=Path.cwd(),
        )
        response_path = evidence.parent / "judge_response.json"
        response_path.write_text(
            json.dumps(
                {
                    "judge_model": "manual-judge-v1",
                    "evidence_hash": packet["evidence_hash"],
                    "verdict": "review",
                    "axis_findings": [
                        {
                            "axis": "pending_questions",
                            "finding": "Questions are useful but should name Finance explicitly.",
                        }
                    ],
                    "disagreements": [
                        {"axis": "pending_questions", "deterministic": "pass", "advisory": "review"}
                    ],
                    "rationale": "Advisory manual judge wants sharper stakeholder assignment.",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
            judge_response_path=response_path,
        )

        self.assertEqual(report["deterministic"]["status"], "pass")
        self.assertEqual(report["advisory_judge"]["status"], "non_blocking")
        self.assertEqual(report["advisory_judge"]["verdict"], "review")
        self.assertEqual(report["advisory_judge"]["judge_model"], "manual-judge-v1")
        self.assertEqual(report["disagreements"][0]["axis"], "pending_questions")
        markdown = (evidence.parent / "report.md").read_text(encoding="utf-8")
        self.assertIn("## Advisory Judge (non-blocking)", markdown)
        self.assertIn("Manual judge verdict: `review`", markdown)
        self.assertIn("pending_questions", markdown)

    def test_datasource_score_blocks_direct_subagent_bypass_before_scoring(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-bypass-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by=None,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "orchestrator_bypass")
        self.assertEqual(report["trace_summary"]["first_brainds_agent"], "brainds-source-explorer")
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "blocked")

    def test_datasource_score_fails_closed_for_fallback_build_agent(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-build-agent-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="build",
                    content_ref="text:assistant:build-agent-response",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="user",
                    content_ref="text:user:subject-prompt",
                    text_hash="b" * 64,
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "wrong_agent")
        self.assertIn("fallback", report["blocking_failures"][0]["message"])

    def test_datasource_score_requires_verifiable_text_exchange(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-missing-text-exchange-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "missing_text_exchange")
        self.assertEqual(report["trace_summary"]["text_exchange"]["status"], "missing")

    def test_datasource_score_requires_subagent_identity_plus_action(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-subagent-identity-only-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "missing_subagent_action")
        self.assertEqual(report["trace_summary"]["subagent_action"]["status"], "missing")

    def test_datasource_score_does_not_credit_tool_calls_without_subagent_identity(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-tool-without-subagent-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds_explore_source",
                    target="source-orders",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "missing_subagent_action")
        self.assertEqual(report["trace_summary"]["subagent_action"]["tool_call_count"], 1)

    def test_datasource_score_does_not_credit_subagent_metadata_events_as_work(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-subagent-metadata-only-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="session_created",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="agent_stream",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "missing_subagent_action")
        self.assertEqual(report["trace_summary"]["subagent_action"]["action_count"], 0)

    def test_datasource_score_blocks_unexpected_primary_fallback_agent_name(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-unexpected-primary-agent-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="verifier",
                    agent_name="build-python",
                    action="agent_stream",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "wrong_agent")
        self.assertEqual(report["trace_summary"]["wrong_or_fallback_agent"], "build-python")

    def test_datasource_score_accepts_orchestrator_first_trace_and_subject_local_freshness(
        self,
    ) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-orchestrated-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["blocking_failures"], [])
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "passed")
        self.assertEqual(report["freshness"]["status"], "passed")

    def test_datasource_score_accepts_normalized_export_alias_lineage(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-normalized-export-alias-lineage",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="opencode:prompt-0000:abcdef123456",
                    text_hash="b" * 64,
                    session_id="ses_orchestrator_alias",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="opencode:text-0001:abcdef123456",
                    text_hash="a" * 64,
                    session_id="ses_orchestrator_alias",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                    session_id="ses_subagent_alias",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["blocking_failures"], [])
        self.assertEqual(
            report["trace_summary"]["first_root_brainds_agent"], "brain-ds-orchestrator"
        )
        self.assertEqual(report["trace_summary"]["subagent_action"]["status"], "verified")
        self.assertIsNone(report["trace_summary"]["wrong_or_fallback_agent"])

    def test_datasource_score_blocks_later_subagent_contact_without_orchestrator_delegation(
        self,
    ) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-late-subagent-bypass-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by=None,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brainds-graph-mapper",
                    delegated_by="manual-verifier",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "orchestrator_bypass")
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "blocked")
        self.assertEqual(
            report["trace_summary"]["undelegated_subagent_contacts"],
            [
                {"agent_name": "brainds-source-explorer", "delegated_by": None},
                {"agent_name": "brainds-graph-mapper", "delegated_by": "manual-verifier"},
            ],
        )

    def test_datasource_score_degrades_stale_or_non_subject_local_freshness(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-stale-freshness-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                ),
            ],
            freshness_status="degraded",
            subject_local_status="failed",
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["freshness"]["status"], "degraded")
        self.assertEqual(report["deterministic"]["status"], "fail")
        self.assertEqual(report["blocking_failures"][0]["code"], "non_subject_local_graph_proof")
        self.assertIn("subject_local_graph", report["freshness"]["failing_checks"])

    def test_datasource_score_reports_ordered_pathway_progression_and_off_path_loops(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-pathway-loop-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                    pathway_milestone="orchestrator_entry",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by="brainds-orchestrator",
                    pathway_milestone="document_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                    action="clarify_same_point",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="subagent",
                    agent_name="brainds-graph-mapper",
                    delegated_by="brainds-orchestrator",
                    pathway_milestone="explore_source",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        compliance = report["pathway_compliance"]
        self.assertEqual(
            compliance["ordered_milestones"],
            ["orchestrator_entry", "explore_source", "document_source", "map_to_graph"],
        )
        self.assertEqual(
            compliance["observed_milestones"],
            ["orchestrator_entry", "document_source", "explore_source"],
        )
        self.assertEqual(compliance["completed_milestones"], ["orchestrator_entry"])
        self.assertEqual(compliance["out_of_order_milestones"], ["explore_source"])
        self.assertEqual(compliance["missing_milestones"], ["map_to_graph"])
        self.assertEqual(compliance["off_path_event_count"], 1)
        self.assertLess(
            report["deterministic"]["conversation_axes"]["pathway_progression"]["score_0_5"], 5
        )

    def test_datasource_score_reports_tool_quality_metrics(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-tool-quality-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                    pathway_milestone="orchestrator_entry",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds.explore_source",
                    target="orders",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="brain_ds.explore_source",
                    target="orders",
                    content_ref="response:success:fields documented",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="unrelated.weather.lookup",
                    target="weather",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:04+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="unrelated.weather.lookup",
                    target="weather",
                    content_ref="response:error:unusable output",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        tool_quality = report["tool_quality"]
        self.assertEqual(tool_quality["tool_call_count"], 2)
        self.assertEqual(tool_quality["tool_response_count"], 2)
        self.assertEqual(tool_quality["successful_response_count"], 1)
        self.assertEqual(tool_quality["irrelevant_tool_calls"], ["unrelated.weather.lookup"])
        self.assertEqual(tool_quality["unusable_output_count"], 1)
        self.assertGreaterEqual(tool_quality["confusion_count"], 1)
        self.assertLess(
            report["deterministic"]["conversation_axes"]["tool_quality"]["score_0_5"], 5
        )

    def test_datasource_tool_quality_score_is_capped_at_five_for_duplicate_responses(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-tool-quality-cap-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brainds-orchestrator",
                    pathway_milestone="orchestrator_entry",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds.explore_source",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="brain_ds.explore_source",
                    content_ref="response:success:source preview",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="brain_ds.explore_source",
                    content_ref="response:success:duplicate source preview",
                    pathway_milestone="explore_source",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["tool_quality"]["tool_call_count"], 1)
        self.assertEqual(report["tool_quality"]["successful_response_count"], 2)
        self.assertEqual(
            report["deterministic"]["conversation_axes"]["tool_quality"]["score_0_5"], 5
        )

    def test_datasource_tool_quality_counts_same_event_completed_output_as_success(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-tool-quality-same-event-success-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds_explore_source",
                    target="orders",
                    pathway_milestone="explore_source",
                    tool_status="completed",
                    tool_output_present=True,
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        tool_quality = report["tool_quality"]
        self.assertEqual(tool_quality["tool_call_count"], 1)
        self.assertEqual(tool_quality["tool_response_count"], 1)
        self.assertEqual(tool_quality["successful_response_count"], 1)
        self.assertEqual(tool_quality["unusable_output_count"], 0)

    def test_datasource_pathway_infers_milestones_from_trace_sequence(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-pathway-inferred-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds_explore_source",
                    target="orders.csv",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="write",
                    target="generated/source_documentation.md",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:04+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds_add_edge",
                    target="helios-datasource-docs",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        compliance = report["pathway_compliance"]
        self.assertEqual(
            compliance["observed_milestones"],
            ["orchestrator_entry", "explore_source", "document_source", "map_to_graph"],
        )
        self.assertEqual(compliance["completed_milestones"], compliance["ordered_milestones"])
        self.assertEqual(
            [item["milestone"] for item in compliance["inferred_milestones"]],
            ["orchestrator_entry", "explore_source", "document_source", "map_to_graph"],
        )

    def test_datasource_generated_axis_accepts_data_quality_caveats_vocabulary(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-vocabulary-tolerant-run",
            generated_text="\n".join(
                [
                    "# Source Documentation",
                    "Owner: RevOps Analytics",
                    "Freshness: updated weekly from warehouse snapshots.",
                    "Data Quality Caveats: null renewal dates require stakeholder confirmation.",
                ]
            ),
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        axis = report["deterministic"]["axes"]["source_documentation"]
        self.assertEqual(axis["score_0_5"], 5)
        self.assertEqual(axis["missing_expected"], [])

    def test_datasource_generated_axis_still_requires_quality_caveats(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-vocabulary-missing-caveat-run",
            generated_text="\n".join(
                [
                    "# Source Documentation",
                    "Owner: RevOps Analytics",
                    "Freshness: updated weekly from warehouse snapshots.",
                    "Columns: order_id, account_id, amount.",
                ]
            ),
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        axis = report["deterministic"]["axes"]["source_documentation"]
        self.assertLess(axis["score_0_5"], 5)
        self.assertIn("data_gap_or_quality_caveat", axis["missing_expected"])

    def test_report_uses_wrapper_model_when_export_model_is_empty(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-wrapper-model-fallback",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
            metadata={"model_provider": "opencode", "wrapper_model": "opencode-go/minimax-m3"},
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(report["comparable_rerun_metadata"]["model"], "opencode-go/minimax-m3")
        self.assertIn(
            "Model: `opencode-go/minimax-m3`",
            (evidence.parent / "report.md").read_text(encoding="utf-8"),
        )

    def test_report_lists_bash_commands_from_trace_tool_calls(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-bash-command-diagnostics-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="bash",
                    target="uv run pytest tests/test_blind_agentic_eval_score.py -q",
                    tool_command="uv run pytest tests/test_blind_agentic_eval_score.py -q",
                    tool_status="completed",
                    tool_output_present=True,
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        self.assertEqual(
            report["tool_quality"]["bash_commands"],
            ["uv run pytest tests/test_blind_agentic_eval_score.py -q"],
        )

    def test_datasource_generate_judge_packet_uses_datasource_failure_status(self) -> None:
        evidence = self._datasource_evidence_bundle(
            "datasource-packet-bypass-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="subagent",
                    agent_name="brainds-source-explorer",
                    delegated_by=None,
                    pathway_milestone="document_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds.explore_source",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="brain_ds.explore_source",
                    content_ref="response:success:source preview",
                    pathway_milestone="explore_source",
                ),
            ],
        )

        packet = generate_judge_packet(
            scenario="datasource_documentation",
            evidence_path=evidence,
            repo_root=Path.cwd(),
        )

        self.assertEqual(packet["deterministic_summary"]["status"], "fail")
        self.assertEqual(packet["trace_summary"]["first_brainds_agent"], "brainds-source-explorer")
        self.assertEqual(
            packet["trace_summary"]["undelegated_subagent_contacts"],
            [{"agent_name": "brainds-source-explorer", "delegated_by": None}],
        )

    def test_datasource_report_and_judge_packet_lock_conversation_contract_fields(self) -> None:
        packet_path = self._test_root / "datasource-contract-packet.json"
        evidence = self._datasource_evidence_bundle(
            "datasource-contract-run",
            events=[
                TraceEvent(
                    ts="2026-06-27T00:00:00+00:00",
                    role="user",
                    content_ref="text:user:prompt",
                    text_hash="b" * 64,
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:01+00:00",
                    role="orchestrator",
                    agent_name="brain-ds-orchestrator",
                    content_ref="text:assistant:reply",
                    text_hash="a" * 64,
                    pathway_milestone="orchestrator_entry",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:02+00:00",
                    role="tool",
                    action="tool_call",
                    tool_name="brain_ds.explore_source",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:03+00:00",
                    role="tool",
                    action="tool_response",
                    tool_name="brain_ds.explore_source",
                    content_ref="response:success:source preview",
                    pathway_milestone="explore_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:04+00:00",
                    role="subagent",
                    agent_name="brain-ds-source-explorer",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                    pathway_milestone="document_source",
                ),
                TraceEvent(
                    ts="2026-06-27T00:00:05+00:00",
                    role="subagent",
                    agent_name="brain-ds-graph-mapper",
                    delegated_by="brain-ds-orchestrator",
                    action="delegated_message",
                    pathway_milestone="map_to_graph",
                ),
            ],
        )

        report = score_evidence(
            scenario="datasource_documentation",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
            judge_packet_out=packet_path,
        )
        persisted = json.loads((evidence.parent / "report.json").read_text(encoding="utf-8"))
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        markdown = (evidence.parent / "report.md").read_text(encoding="utf-8")

        self.assertIn("conversation_axes", persisted["deterministic"])
        self.assertIn("pathway_compliance", persisted)
        self.assertIn("tool_quality", persisted)
        self.assertEqual(persisted["deterministic"]["status"], "pass")
        self.assertEqual(
            persisted["deterministic"]["conversation_axes"],
            {
                "pathway_progression": {
                    "score_0_5": 5,
                    "rationale": "Ordered datasource milestones advance without off-path loops.",
                    "evidence_refs": ["trace/session_trace.json"],
                },
                "tool_quality": {
                    "score_0_5": 5,
                    "rationale": "Tool calls are relevant and responses are successful and usable.",
                    "evidence_refs": ["trace/session_trace.json"],
                },
            },
        )
        self.assertEqual(
            persisted["pathway_compliance"],
            {
                "ordered_milestones": [
                    "orchestrator_entry",
                    "explore_source",
                    "document_source",
                    "map_to_graph",
                ],
                "observed_milestones": [
                    "orchestrator_entry",
                    "explore_source",
                    "document_source",
                    "map_to_graph",
                ],
                "inferred_milestones": [],
                "completed_milestones": [
                    "orchestrator_entry",
                    "explore_source",
                    "document_source",
                    "map_to_graph",
                ],
                "missing_milestones": [],
                "out_of_order_milestones": [],
                "off_path_event_count": 0,
                "progression_ratio": 1.0,
            },
        )
        self.assertEqual(
            persisted["tool_quality"],
            {
                "tool_call_count": 1,
                "tool_response_count": 1,
                "successful_response_count": 1,
                "relevant_tool_call_count": 1,
                "irrelevant_tool_calls": [],
                "unusable_output_count": 0,
                "confusion_count": 0,
            },
        )
        self.assertEqual(packet["packet_version"], 2)
        self.assertEqual(packet["deterministic_summary"], persisted["deterministic"])
        self.assertEqual(packet["trace_summary"], report["trace_summary"])
        self.assertEqual(packet["conversation_axes"], report["deterministic"]["conversation_axes"])
        self.assertEqual(packet["pathway_compliance"], report["pathway_compliance"])
        self.assertEqual(packet["tool_quality"], report["tool_quality"])
        self.assertIn("## Pathway Compliance", markdown)
        self.assertIn("## Tool Quality", markdown)

    def test_score_report_emits_path_matrix_payload_and_interpretation_lanes(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-output-contract",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )

        report = score_evidence(
            scenario="revops_growth",
            evidence_path=evidence,
            out_path=evidence.parent / "report.json",
            repo_root=Path.cwd(),
        )

        selected_path = report["selected_path"]
        self.assertEqual(selected_path["scenario"], "graph_qa")
        self.assertEqual(
            selected_path["required_evidence"],
            ["manifest.json", "session_trace.json", "graph/store.db"],
        )
        self.assertEqual(selected_path["expected_artifacts"], ["report.json", "report.md"])
        self.assertEqual(selected_path["scorer"], "deterministic-local-evidence")
        self.assertEqual(selected_path["rubric_version"], "agentic-eval-rubric.v1")
        self.assertEqual(selected_path["output_contract"], "blind-agentic-report.v1")
        self.assertEqual(report["freshness"]["report_schema_version"], "2026-06-30.pr3")
        self.assertEqual(report["comparability"]["status"], "comparable")
        self.assertEqual(report["comparability"]["key"]["path_id"], "graph-qa")

        lanes = {lane["lane"]: lane for lane in report["interpretation"]}
        self.assertEqual(
            set(lanes),
            {"artifact_quality", "flow_tool_delegation_quality", "model_capability_context"},
        )
        for lane in lanes.values():
            self.assertIn(lane["status"], {"pass", "warn", "fail", "not_applicable"})
            self.assertTrue(lane["evidence_refs"])

    def test_score_report_rejects_missing_output_contract_fields(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-missing-output-contract",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("selected_path")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with self.assertRaisesRegex(ScoreReportError, "selected_path"):
            score_evidence(
                scenario="revops_growth",
                evidence_path=evidence,
                out_path=evidence.parent / "report.json",
                repo_root=Path.cwd(),
            )

    def test_score_report_rejects_invalid_lineage_sdd_change(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-invalid-lineage-sdd",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["lineage"]["sdd_change"] = "Agentic-Evaluation-Lab"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with self.assertRaisesRegex(ScoreReportError, "lineage.*sdd_change"):
            score_evidence(
                scenario="revops_growth",
                evidence_path=evidence,
                out_path=evidence.parent / "report.json",
                repo_root=Path.cwd(),
            )

    def test_score_report_rejects_incomplete_comparability_key(self) -> None:
        evidence = self._graph_evidence_bundle(
            "score-run-incomplete-comparability-key",
            include_all_expected=True,
            generated_text=self._business_generated_text_without_lineage_ids(),
        )
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["comparability"]["key"].pop("git_diff_hash")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with self.assertRaisesRegex(ScoreReportError, "comparability.key.*git_diff_hash"):
            score_evidence(
                scenario="revops_growth",
                evidence_path=evidence,
                out_path=evidence.parent / "report.json",
                repo_root=Path.cwd(),
            )

    def _evidence_bundle(
        self,
        run_id: str,
        *,
        generated_text: str,
        metadata: dict[str, object] | None = None,
    ) -> Path:
        evidence = self._test_root / run_id / "evidence"
        generated = evidence / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "diagnosis.md").write_text(generated_text, encoding="utf-8")
        (evidence / "graph").mkdir(parents=True, exist_ok=True)
        (evidence / "graph" / "store.db").write_bytes(b"sqlite graph snapshot")
        (evidence / "git_diff.patch").write_text(
            "diff --git a/generated/diagnosis.md b/generated/diagnosis.md", encoding="utf-8"
        )

        manifest = {
            "scenario": "revops_growth",
            "run_id": run_id,
            "created_at_utc": "2026-06-26T00:00:00+00:00",
            "captured": {
                "graph_db": "graph/store.db",
                "generated_outputs": ["generated/diagnosis.md"],
                "git_diff": "git_diff.patch",
            },
            "minimum_evidence": {
                "status": "accepted",
                "reason": "graph snapshot plus output/diff evidence captured",
            },
            "anti_contamination": {"status": "passed", "findings": []},
            "run_metadata": {
                "prompt_version": "revops-growth-v1",
                "fixture_version": "revops-growth-fixture-v1",
                **(metadata or {}),
            },
            "lineage": {
                "commit_sha": "abc123def456",
                "sdd_change": "agentic-evaluation-lab",
                "worktree_dirty": False,
                "git_diff_hash": None,
                "untracked_files_present": False,
                "captured_at_utc": "2026-06-30T00:00:00Z",
            },
            "path_plan_version": "2026-06-30.pr1",
            "selected_path": {
                "path_id": "graph-qa",
                "path_plan_version": "2026-06-30.pr1",
                "label": "Graph Q&A dossier answer",
                "scenario": "graph_qa",
                "agents_or_tools": ["brainds-query-consultant"],
                "required_evidence": ["manifest.json", "session_trace.json", "graph/store.db"],
                "expected_artifacts": ["report.json", "report.md"],
                "scorer": "deterministic-local-evidence",
                "rubric_version": "agentic-eval-rubric.v1",
                "output_contract": "blind-agentic-report.v1",
                "status": "required",
                "execute_in_first_slice": True,
            },
            "comparability": {
                "status": "comparable",
                "reason": None,
                "key": {
                    "commit_sha": "abc123def456",
                    "worktree_dirty": False,
                    "git_diff_hash": None,
                    "untracked_files_present": False,
                    "sdd_change": "agentic-evaluation-lab",
                    "path_id": "graph-qa",
                    "path_plan_version": "2026-06-30.pr1",
                    "scenario": "graph_qa",
                    "prompt_version": "revops-growth-v1",
                    "rubric_version": "agentic-eval-rubric.v1",
                    "trace_schema_version": "2026-06-27.pr1",
                    "report_schema_version": "2026-06-30.pr3",
                },
            },
        }
        (evidence / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return evidence

    def _datasource_evidence_bundle(
        self,
        run_id: str,
        *,
        events: list[TraceEvent] | None = None,
        freshness_status: str = "passed",
        subject_local_status: str = "passed",
        generated_text: str | None = None,
    ) -> Path:
        evidence = self._test_root / run_id / "evidence"
        generated = evidence / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "source_documentation.md").write_text(
            generated_text
            or "# Source Documentation\n\nOrders and Customers have owners, freshness cadence, and data gaps.",
            encoding="utf-8",
        )
        (evidence / "git_diff.patch").write_text(
            "diff --git a/generated/source_documentation.md", encoding="utf-8"
        )
        graph_db = evidence / "graph" / "store.db"
        graph_db.parent.mkdir(parents=True, exist_ok=True)
        graph_db.unlink(missing_ok=True)
        with GraphStore(str(graph_db)) as store:
            store.create_graph("helios-datasource-docs", name="Helios Retail Source Documentation")
            for node in [
                {"id": "source-orders", "label": "Orders", "type": "Data Source"},
                {"id": "source-customers", "label": "Customers", "type": "Data Source"},
            ]:
                store.node_repo.upsert_node("helios-datasource-docs", {**node, "details": {}})
            store.edge_repo.upsert_edge(
                "helios-datasource-docs",
                {
                    "source": "source-orders",
                    "target": "source-customers",
                    "label": "uses",
                    "weight": 1.0,
                },
            )
        trace = SessionTrace(
            trace_version=TRACE_VERSION,
            run_id=run_id,
            scenario="datasource_documentation",
            pathway_id="datasource_documentation",
            model_provider="opencode",
            model="test-model",
            created_at_utc="2026-06-27T00:00:00+00:00",
            events=events or [],
            freshness={"status": freshness_status, "schema_version": TRACE_VERSION},
        )
        trace_hash = write_session_trace(trace, evidence / "trace" / "session_trace.json")
        manifest = {
            "scenario": "datasource_documentation",
            "run_id": run_id,
            "created_at_utc": "2026-06-27T00:00:00+00:00",
            "captured": {
                "graph_db": "graph/store.db",
                "graph_id": "helios-datasource-docs",
                "generated_outputs": ["generated/source_documentation.md"],
                "git_diff": "git_diff.patch",
                "session_trace": "trace/session_trace.json",
            },
            "trace": {
                "status": "captured",
                "path": "trace/session_trace.json",
                "sha256": trace_hash["sha256"],
                "event_count": len(events or []),
            },
            "freshness_checks": {
                "status": freshness_status,
                "report_schema_version": "2026-06-27.pr2",
                "trace_schema_version": TRACE_VERSION,
                "subject_local_graph": {
                    "status": subject_local_status,
                    "reason": "subject workspace graph required",
                },
                "generated_outputs": {"status": "captured"},
                "trace": {"status": "captured"},
                "artifact_hashes": {
                    "graph/store.db": "a" * 64,
                    "generated/source_documentation.md": "b" * 64,
                },
            },
            "minimum_evidence": {
                "status": "accepted",
                "reason": "graph snapshot plus output/diff evidence captured",
            },
            "anti_contamination": {"status": "passed", "findings": []},
            "run_metadata": {
                "prompt_version": "datasource-documentation-v1",
                "fixture_version": "datasource-documentation-fixture-v1",
            },
            "lineage": {
                "commit_sha": "abc123def456",
                "sdd_change": "agentic-evaluation-lab",
                "worktree_dirty": False,
                "git_diff_hash": None,
                "untracked_files_present": False,
                "captured_at_utc": "2026-06-30T00:00:00Z",
            },
            "path_plan_version": "2026-06-30.pr1",
            "selected_path": {
                "path_id": "doc-map",
                "path_plan_version": "2026-06-30.pr1",
                "label": "Source documentation to graph mapping",
                "scenario": "datasource_documentation",
                "agents_or_tools": [
                    "brainds-source-explorer",
                    "brainds-graph-mapper",
                    "brainds-connection-mapper",
                ],
                "required_evidence": ["manifest.json", "session_trace.json", "graph/store.db"],
                "expected_artifacts": ["report.json", "report.md"],
                "scorer": "deterministic-local-evidence",
                "rubric_version": "agentic-eval-rubric.v1",
                "output_contract": "blind-agentic-report.v1",
                "status": "required",
                "execute_in_first_slice": True,
            },
            "comparability": {
                "status": "comparable",
                "reason": None,
                "key": {
                    "commit_sha": "abc123def456",
                    "worktree_dirty": False,
                    "git_diff_hash": None,
                    "untracked_files_present": False,
                    "sdd_change": "agentic-evaluation-lab",
                    "path_id": "doc-map",
                    "path_plan_version": "2026-06-30.pr1",
                    "scenario": "datasource_documentation",
                    "prompt_version": "datasource-documentation-v1",
                    "rubric_version": "agentic-eval-rubric.v1",
                    "trace_schema_version": TRACE_VERSION,
                    "report_schema_version": "2026-06-30.pr3",
                },
            },
        }
        (evidence / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return evidence

    def _graph_evidence_bundle(
        self,
        run_id: str,
        *,
        include_all_expected: bool = False,
        include_unknown_alias: bool = False,
        include_forbidden_edge: bool = False,
        include_optional_edge: bool = False,
        generated_text: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Path:
        evidence = self._evidence_bundle(
            run_id,
            generated_text=generated_text or self._complete_generated_text(),
            metadata=metadata,
        )
        graph_db = evidence / "graph" / "store.db"
        graph_db.unlink(missing_ok=True)
        with GraphStore(str(graph_db)) as store:
            store.create_graph("revops_graph", name="RevOps Growth")
            nodes = [
                {"id": "mkt", "label": "MKT Campaigns", "type": "Data Source"},
                {"id": "pipeline", "label": "Marketing Influenced Pipeline", "type": "KPI"},
            ]
            edges = [{"source": "mkt", "target": "pipeline", "label": "influences", "weight": 1.0}]
            pending: list[PendingQuestionInput] = [
                {
                    "target_node_id": "mkt",
                    "gap_kind": "ownership",
                    "entity_type": "Data Source",
                    "question_text": "Who is the accountable source owner?",
                    "stakeholder_owner": "RevOps",
                }
            ]
            if include_all_expected:
                nodes.extend(
                    [
                        {"id": "crm", "label": "Customer Accounts", "type": "Data Source"},
                        {"id": "billing", "label": "Subscription Billing", "type": "Data Source"},
                        {"id": "finance", "label": "Revenue Ledger", "type": "Data Source"},
                        {"id": "usage", "label": "Product Telemetry", "type": "Data Source"},
                        {"id": "support", "label": "Support Cases", "type": "Data Source"},
                        {"id": "nrr", "label": "Net Revenue Retention", "type": "KPI"},
                    ]
                )
                edges.extend(
                    [
                        {
                            "source": "crm",
                            "target": "pipeline",
                            "label": "depends on",
                            "weight": 1.0,
                        },
                        {
                            "source": "billing",
                            "target": "nrr",
                            "label": "depends_on",
                            "weight": 1.0,
                        },
                        {"source": "finance", "target": "nrr", "label": "measures", "weight": 1.0},
                        {"source": "usage", "target": "nrr", "label": "uses", "weight": 1.0},
                        {
                            "source": "support",
                            "target": "nrr",
                            "label": "influences",
                            "weight": 1.0,
                        },
                    ]
                )
                pending.extend(
                    [
                        {
                            "target_node_id": "nrr",
                            "gap_kind": "definition",
                            "entity_type": "KPI",
                            "question_text": "Confirm the calculation definition and threshold for NRR.",
                            "stakeholder_owner": "Finance",
                        },
                        {
                            "target_node_id": None,
                            "gap_kind": "data_gap",
                            "entity_type": None,
                            "question_text": "Confirm missing data gap before final diagnosis.",
                            "stakeholder_owner": "Data Engineering",
                        },
                    ]
                )
            if include_unknown_alias:
                nodes.append(
                    {"id": "finance", "label": "Ledger Not In Gold", "type": "Data Source"}
                )
            if include_forbidden_edge:
                nodes.append({"id": "support", "label": "Support Cases", "type": "Data Source"})
                edges.append(
                    {"source": "support", "target": "pipeline", "label": "measures", "weight": 1.0}
                )
            if include_optional_edge:
                edges.append(
                    {"source": "nrr", "target": "billing", "label": "measured_from", "weight": 1.0}
                )
            for node in nodes:
                store.node_repo.upsert_node("revops_graph", {**node, "details": {}})
            for edge in edges:
                store.edge_repo.upsert_edge("revops_graph", edge)
            for question in pending:
                store.insert_pending_question("revops_graph", **question)
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        manifest["captured"]["graph_id"] = "revops_graph"
        (evidence / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return evidence

    def _subject_workspace_with_graph(
        self,
        run_id: str,
        *,
        include_all_expected: bool = False,
        generated_text: str | None = None,
    ) -> Path:
        subject = self._test_root / run_id / "subject"
        generated = subject / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "diagnosis.md").write_text(
            generated_text or self._complete_generated_text(), encoding="utf-8"
        )
        graph_db = subject / ".brain_ds" / "store.db"
        graph_db.parent.mkdir(parents=True, exist_ok=True)
        graph_db.unlink(missing_ok=True)
        with GraphStore(str(graph_db)) as store:
            store.create_graph("revops_graph", name="RevOps Growth")
            nodes = [
                {"id": "mkt", "label": "MKT Campaigns", "type": "Data Source"},
                {"id": "pipeline", "label": "Marketing Influenced Pipeline", "type": "KPI"},
            ]
            edges = [{"source": "mkt", "target": "pipeline", "label": "influences", "weight": 1.0}]
            if include_all_expected:
                nodes.extend(
                    [
                        {"id": "crm", "label": "Customer Accounts", "type": "Data Source"},
                        {"id": "billing", "label": "Subscription Billing", "type": "Data Source"},
                        {"id": "finance", "label": "Revenue Ledger", "type": "Data Source"},
                        {"id": "usage", "label": "Product Telemetry", "type": "Data Source"},
                        {"id": "support", "label": "Support Cases", "type": "Data Source"},
                        {"id": "nrr", "label": "Net Revenue Retention", "type": "KPI"},
                    ]
                )
                edges.extend(
                    [
                        {
                            "source": "crm",
                            "target": "pipeline",
                            "label": "depends_on",
                            "weight": 1.0,
                        },
                        {
                            "source": "billing",
                            "target": "nrr",
                            "label": "depends_on",
                            "weight": 1.0,
                        },
                        {"source": "finance", "target": "nrr", "label": "measures", "weight": 1.0},
                        {"source": "usage", "target": "nrr", "label": "uses", "weight": 1.0},
                        {
                            "source": "support",
                            "target": "nrr",
                            "label": "influences",
                            "weight": 1.0,
                        },
                    ]
                )
            for node in nodes:
                store.node_repo.upsert_node("revops_graph", {**node, "details": {}})
            for edge in edges:
                store.edge_repo.upsert_edge("revops_graph", edge)
        return subject

    def _complete_generated_text(self) -> str:
        return "\n".join(
            [
                "# Revenue Operations Diagnosis",
                "Pipeline lineage uses marketing_campaigns and crm_accounts.",
                "Conversion lineage uses marketing_campaigns and crm_accounts.",
                "Retention lineage uses billing_subscriptions, product_usage, and support_tickets.",
                "Expansion lineage uses billing_subscriptions, finance_revenue, and product_usage.",
                "Net revenue retention lineage uses billing_subscriptions, finance_revenue, and support_tickets.",
                "Evidence references generated artifacts, graph store, git diff, and assumptions.",
                "Business next actions: reconcile source ownership, fix KPI definitions, and document data gaps.",
            ]
        )

    def _business_generated_text_without_lineage_ids(self) -> str:
        return "\n".join(
            [
                "# Revenue Operations Diagnosis",
                "Evidence references generated artifacts, graph store, git diff, and assumptions.",
                "Business next actions: reconcile source ownership, fix KPI definitions, and document data gaps.",
            ]
        )
