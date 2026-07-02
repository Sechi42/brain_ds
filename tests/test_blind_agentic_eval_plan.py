import unittest
from pathlib import Path
from unittest.mock import patch

from tests.eval.blind_agentic import collect_and_score, run_opencode_verifier
from tests.eval.blind_agentic.path_plan import (
    INTERPRETATION_LANES,
    PLAN_VERSION,
    PathPlanError,
    build_comparability_state,
    build_default_plan,
    build_interpretation_lane,
    discover_git_lineage,
    ensure_single_path_selection,
    build_lineage,
    normalize_requested_path,
    validate_sdd_change,
)

SDD_CHANGE = "agentic-evaluation-lab"
STAMP = "2026-06-30T12:00:00+00:00"


def _lineage(status_porcelain: str = "", git_diff: str = ""):
    return build_lineage(
        commit_sha="abc123def456",
        sdd_change=SDD_CHANGE,
        status_porcelain=status_porcelain,
        git_diff=git_diff,
        captured_at_utc=STAMP,
    )


def _comparability(lineage, path_id: str = "doc-map"):
    return build_comparability_state(
        lineage=lineage,
        selected_path=build_default_plan(sdd_change=SDD_CHANGE).path_by_id(path_id),
        prompt_version="prompt.v1",
        trace_schema_version="trace.v1",
        report_schema_version="report.v1",
    )


class BlindAgenticEvaluationPlanTests(unittest.TestCase):
    def test_sdd_change_is_required_and_slug_validated(self) -> None:
        self.assertEqual(validate_sdd_change(SDD_CHANGE), SDD_CHANGE)

        for value in ("", "Agentic Evaluation", "agentic_eval", "-agentic"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(PathPlanError, "sdd_change"):
                    validate_sdd_change(value)

    def test_lineage_records_clean_commit_and_comparable_key_includes_path_version(self) -> None:
        lineage = _lineage()
        comparability = _comparability(lineage)

        self.assertFalse(lineage.worktree_dirty)
        self.assertIsNone(lineage.git_diff_hash)
        self.assertEqual(comparability.status, "comparable")
        self.assertEqual(comparability.key["commit_sha"], "abc123def456")
        self.assertEqual(comparability.key["path_id"], "doc-map")
        self.assertEqual(comparability.key["path_plan_version"], PLAN_VERSION)
        self.assertEqual(comparability.key["sdd_change"], SDD_CHANGE)

    def test_dirty_tracked_lineage_hashes_diff_for_same_diff_comparison(self) -> None:
        lineage = _lineage(
            status_porcelain=" M tests/eval/blind_agentic/path_plan.py\n",
            git_diff="diff --git a/file b/file\n+changed\n",
        )
        comparability = _comparability(lineage, "graph-qa")

        self.assertTrue(lineage.worktree_dirty)
        self.assertIsNotNone(lineage.git_diff_hash)
        self.assertEqual(len(lineage.git_diff_hash or ""), 64)
        self.assertEqual(comparability.status, "non_comparable")
        self.assertEqual(comparability.reason, "tracked_source_drift")
        self.assertIsNone(comparability.key)

    def test_discover_git_lineage_hashes_staged_only_tracked_diff(self) -> None:
        responses = {
            ("rev-parse", "HEAD"): "abc123def456\n",
            ("status", "--porcelain"): "M  tests/eval/blind_agentic/path_plan.py\n",
            ("diff",): "",
            ("diff", "--cached"): "diff --git a/file b/file\n+staged\n",
        }

        with patch(
            "tests.eval.blind_agentic.path_plan._git",
            side_effect=lambda _root, *args: responses[args],
        ):
            lineage = discover_git_lineage(Path.cwd(), sdd_change=SDD_CHANGE)

        self.assertTrue(lineage.worktree_dirty)
        self.assertIsNotNone(lineage.git_diff_hash)
        self.assertEqual(len(lineage.git_diff_hash or ""), 64)

    def test_path_selection_maps_revops_fixture_to_graph_qa_and_rejects_unknown(self) -> None:
        plan = build_default_plan(sdd_change=SDD_CHANGE)

        self.assertEqual(plan.path_for_scenario("revops_growth").path_id, "graph-qa")
        self.assertEqual(plan.path_for_scenario("graph_qa").path_id, "graph-qa")
        with self.assertRaisesRegex(PathPlanError, "Unknown scenario"):
            plan.path_for_scenario("unknown_scenario")

    def test_requested_path_normalization_preserves_external_path_identity(self) -> None:
        graph_qa = normalize_requested_path("graph-qa", sdd_change=SDD_CHANGE)
        doc_map = normalize_requested_path("doc-map", sdd_change=SDD_CHANGE)

        self.assertEqual(graph_qa.path_id, "graph-qa")
        self.assertEqual(graph_qa.scenario, "revops_growth")
        self.assertEqual(graph_qa.plan_entry.path_id, "graph-qa")
        self.assertEqual(doc_map.path_id, "doc-map")
        self.assertEqual(doc_map.scenario, "datasource_documentation")
        self.assertEqual(doc_map.plan_entry.path_id, "doc-map")

    def test_requested_path_normalization_accepts_fixture_scenario_aliases(self) -> None:
        graph_qa = normalize_requested_path("revops_growth", sdd_change=SDD_CHANGE)
        doc_map = normalize_requested_path("datasource_documentation", sdd_change=SDD_CHANGE)

        self.assertEqual(graph_qa.path_id, "graph-qa")
        self.assertEqual(graph_qa.scenario, "revops_growth")
        self.assertEqual(doc_map.path_id, "doc-map")
        self.assertEqual(doc_map.scenario, "datasource_documentation")

    def test_requested_path_normalization_rejects_unknown_path(self) -> None:
        with self.assertRaisesRegex(PathPlanError, "Unknown path_id or scenario"):
            normalize_requested_path("unknown-path", sdd_change=SDD_CHANGE)

    def test_single_path_guard_rejects_comparative_inputs_before_execution(self) -> None:
        self.assertEqual(ensure_single_path_selection("graph-qa"), "graph-qa")

        for value in (["graph-qa", "doc-map"], "graph-qa,doc-map", "graph-qa vs doc-map"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(PathPlanError, "one path"):
                    ensure_single_path_selection(value)

    def test_run_opencode_verifier_cli_accepts_path_id_and_normalizes_scenario(self) -> None:
        with patch.object(run_opencode_verifier, "run_verifier") as run_verifier:
            run_verifier.return_value = run_opencode_verifier.OpenCodeVerifierResult(
                scenario="revops_growth",
                path_id="graph-qa",
                run_id="path-id-run",
                subject_path=Path("subject"),
                manifest_path=Path("manifest.json"),
                export_path=Path("session.json"),
                session_id="ses_123",
            )

            exit_code = run_opencode_verifier.main(["--path-id", "graph-qa", "--run-id", "path-id-run"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(run_verifier.call_args.kwargs["scenario"], "revops_growth")
        self.assertEqual(run_verifier.call_args.kwargs["path_id"], "graph-qa")

    def test_collect_and_score_cli_accepts_path_id_and_scores_normalized_scenario(self) -> None:
        with patch.object(collect_and_score, "collect_evidence") as collect_evidence:
            with patch.object(collect_and_score, "score_evidence") as score_evidence:
                collect_evidence.return_value.evidence_path = Path("evidence")
                collect_evidence.return_value.manifest_path = Path("evidence/manifest.json")
                score_evidence.return_value = {
                    "scenario": "datasource_documentation",
                    "selected_path": {"path_id": "doc-map", "scenario": "datasource_documentation"},
                    "overall_score_0_5": 5.0,
                }

                exit_code = collect_and_score.main(["--path-id", "doc-map", "--run-id", "path-score-run"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(collect_evidence.call_args.kwargs["scenario"], "datasource_documentation")
        self.assertEqual(score_evidence.call_args.kwargs["scenario"], "datasource_documentation")

    def test_untracked_files_are_non_comparable_and_not_covered_by_diff_hash(self) -> None:
        lineage = _lineage(status_porcelain="?? scratch.md\n")
        comparability = _comparability(lineage)

        self.assertTrue(lineage.untracked_files_present)
        self.assertIsNone(lineage.git_diff_hash)
        self.assertEqual(comparability.status, "non_comparable")
        self.assertEqual(comparability.reason, "untracked_files_not_captured")
        self.assertIsNone(comparability.key)

    def test_allowlisted_generated_untracked_eval_outputs_remain_comparable(self) -> None:
        lineage = _lineage(status_porcelain="?? tmp/blind-agentic-eval/run_001/report.json\n")

        comparability = _comparability(lineage)

        self.assertEqual(comparability.status, "comparable")
        self.assertEqual(
            comparability.key["ignored_untracked_files"],
            ["tmp/blind-agentic-eval/run_001/report.json"],
        )

    def test_non_allowlisted_untracked_source_drift_stays_non_comparable(self) -> None:
        lineage = _lineage(
            status_porcelain="?? tmp/blind-agentic-eval/run_001/report.json\n?? brain_ds/new_feature.py\n"
        )

        comparability = _comparability(lineage)

        self.assertEqual(comparability.status, "non_comparable")
        self.assertEqual(comparability.reason, "untracked_files_not_captured")
        self.assertIsNone(comparability.key)

    def test_default_path_matrix_contains_required_entries_and_planned_only_candidates(
        self,
    ) -> None:
        plan = build_default_plan(sdd_change=SDD_CHANGE)

        self.assertEqual(plan.path_plan_version, PLAN_VERSION)
        self.assertEqual(
            [entry.path_id for entry in plan.required_entries()], ["doc-map", "graph-qa"]
        )
        for path_id in ("doc-map", "graph-qa"):
            entry = plan.path_by_id(path_id)
            self.assertEqual(entry.status, "required")
            self.assertTrue(entry.execute_in_first_slice)
            self.assertTrue(entry.required_evidence)
            self.assertTrue(entry.expected_artifacts)
            self.assertTrue(entry.scorer and entry.rubric_version and entry.output_contract)

        candidates = [entry for entry in plan.entries if entry.status == "candidate"]
        self.assertEqual(candidates, [])

    def test_supported_slice2_paths_are_executable_only_after_fixture_and_gold_registration(
        self,
    ) -> None:
        plan = build_default_plan(sdd_change=SDD_CHANGE)

        for path_id, scenario in (
            ("kpi-lineage", "kpi_lineage"),
            ("currency-elicitation", "currency_elicitation"),
        ):
            with self.subTest(path_id=path_id):
                entry = plan.path_by_id(path_id)
                self.assertEqual(entry.status, "supported")
                self.assertTrue(entry.execute_in_first_slice)
                self.assertEqual(entry.scenario, scenario)
                self.assertEqual(plan.path_for_scenario(scenario).path_id, path_id)

                fixture_root = Path(__file__).parent / "fixtures" / "blind_agentic" / scenario
                gold_root = Path(__file__).parent / "gold" / "blind_agentic" / scenario
                self.assertTrue((fixture_root / "PROMPT.md").is_file())
                self.assertTrue((fixture_root / "seed_graph.json").is_file())
                self.assertTrue((gold_root / "gold_v2.json").is_file())

        candidates = [entry.path_id for entry in plan.entries if entry.status == "candidate"]
        self.assertNotIn("kpi-lineage", candidates)
        self.assertNotIn("currency-elicitation", candidates)

    def test_interpretation_lane_vocabulary_and_evidence_refs_are_explicit(self) -> None:
        lane = build_interpretation_lane(
            lane="artifact_quality",
            status="warn",
            evidence_refs=["manifest:minimum_evidence"],
        )

        self.assertEqual(
            INTERPRETATION_LANES,
            ("artifact_quality", "flow_tool_delegation_quality", "model_capability_context"),
        )
        self.assertEqual(lane["lane"], "artifact_quality")
        self.assertEqual(lane["status"], "warn")
        self.assertEqual(lane["evidence_refs"], ["manifest:minimum_evidence"])

        with self.assertRaisesRegex(PathPlanError, "interpretation"):
            build_interpretation_lane(lane="model_score", status="pass", evidence_refs=["x"])
