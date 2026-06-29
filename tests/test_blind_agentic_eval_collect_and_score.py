from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TypedDict

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic import collect_and_score
from tests.eval.blind_agentic.prepare_subject import prepare_subject


class _PendingQuestion(TypedDict):
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str


class BlindAgenticCollectAndScoreCliTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(Path("tmp") / "blind-agentic-collect-score-test", ignore_errors=True)

    def test_collect_and_score_cli_fails_clearly_when_graph_db_is_missing(self) -> None:
        run_id = "collect-score-missing-graph"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        generated = workspace.subject_path / ".elicit"
        generated.mkdir()
        (generated / "brd.md").write_text("# BRD\n\nPipeline lineage mapped.", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.collect_and_score",
                "--scenario",
                "revops_growth",
                "--run-id",
                run_id,
                "--subject-path",
                workspace.subject_path.as_posix(),
                "--repo-root",
                Path.cwd().as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing graph snapshot", result.stderr)
        self.assertIn("--graph-db-path", result.stderr)

    def test_collect_and_score_cli_collects_override_and_writes_report(self) -> None:
        run_id = "collect-score-override"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_subject_outputs(workspace.subject_path)
        graph_db = workspace.subject_path.parent / "external-workspace" / ".brain_ds" / "store.db"
        self._write_graph_store(graph_db)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.collect_and_score",
                "--scenario",
                "revops_growth",
                "--run-id",
                run_id,
                "--subject-path",
                workspace.subject_path.as_posix(),
                "--repo-root",
                Path.cwd().as_posix(),
                "--graph-db-path",
                graph_db.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Evidence manifest:", result.stdout)
        self.assertIn("Score report:", result.stdout)
        report_path = workspace.subject_path.parent / "report.json"
        manifest_path = workspace.subject_path.parent / "evidence" / "manifest.json"
        self.assertTrue(report_path.is_file())
        self.assertTrue(manifest_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["run_id"], run_id)

    def test_collect_and_score_cli_accepts_optional_graph_id_and_packet_output(self) -> None:
        run_id = "collect-score-judge"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_subject_outputs(workspace.subject_path)
        graph_db = workspace.subject_path.parent / "external-workspace" / ".brain_ds" / "store.db"
        self._write_graph_store(graph_db)
        packet_out = workspace.subject_path.parent / "judge_packet.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.collect_and_score",
                "--scenario",
                "revops_growth",
                "--run-id",
                run_id,
                "--subject-path",
                workspace.subject_path.as_posix(),
                "--repo-root",
                Path.cwd().as_posix(),
                "--graph-db-path",
                graph_db.as_posix(),
                "--graph-id",
                "revops_graph",
                "--judge-packet-out",
                packet_out.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(packet_out.is_file())
        packet = json.loads(packet_out.read_text(encoding="utf-8"))
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(report["advisory_judge"])
        self.assertEqual(
            packet["evidence_hash"],
            report["evidence_hash"],
        )
        self.assertEqual(packet["generated_excerpts"][0]["path"], "generated/diagnosis.md")
        self.assertIn("Pipeline lineage", packet["generated_excerpts"][0]["excerpt"])
        self.assertEqual(packet["missing_items"]["artifact_classes"], ["setup_metadata"])

    def test_collect_and_score_main_reports_advisory_hash_mismatch_directly(self) -> None:
        run_id = "collect-score-direct-mismatch"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_subject_outputs(workspace.subject_path)
        graph_db = workspace.subject_path.parent / "external-workspace" / ".brain_ds" / "store.db"
        self._write_graph_store(graph_db)
        judge_response = workspace.subject_path.parent / "judge_response.json"
        judge_response.write_text(
            json.dumps(
                {
                    "judge_model": "manual-judge",
                    "evidence_hash": "not-the-collected-evidence-hash",
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

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "revops_growth",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--graph-db-path",
                    graph_db.as_posix(),
                    "--judge-response",
                    judge_response.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("error:", stderr.getvalue())
        self.assertIn("evidence hash", stderr.getvalue())

    def test_collect_and_score_main_adds_double_verifier_audit_fields(self) -> None:
        run_id = "collect-score-double-verifier"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_subject_outputs(workspace.subject_path)
        graph_db = workspace.subject_path.parent / "external-workspace" / ".brain_ds" / "store.db"
        self._write_graph_store(graph_db)
        audit_path = workspace.subject_path.parent / "verifier_b_audit.json"
        audit_path.write_text(
            json.dumps(
                {
                    "verifier_b_model": "audit-model-b",
                    "confirmations": ["Lineage evidence is supported."],
                    "challenges": ["Freshness should be checked before comparing models."],
                    "refinements": ["Compare only runs with matching fixture versions."],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "revops_growth",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--graph-db-path",
                    graph_db.as_posix(),
                    "--verifier-a-model",
                    "execution-model-a",
                    "--verifier-b-audit",
                    audit_path.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertIn("Double-verifier audit:", stdout.getvalue())
        self.assertEqual(report["double_verifier"]["verifier_a_model"], "execution-model-a")
        self.assertEqual(report["double_verifier"]["verifier_b_model"], "audit-model-b")
        self.assertEqual(report["double_verifier"]["audit_status"], "challenged")
        self.assertEqual(
            report["double_verifier"]["challenges"],
            ["Freshness should be checked before comparing models."],
        )

    def test_collect_and_score_main_writes_same_pathway_model_matrix(self) -> None:
        comparison_root = Path("tmp") / "blind-agentic-collect-score-test" / "comparison"
        comparison_root.mkdir(parents=True, exist_ok=True)
        report_a = self._write_report_for_comparison(
            comparison_root / "model-a-report.json",
            run_id="model-a-run",
            model="model-a",
            score=4.5,
            schema_version="2026-06-27.pr4",
        )
        report_b = self._write_report_for_comparison(
            comparison_root / "model-b-report.json",
            run_id="model-b-run",
            model="model-b",
            score=3.25,
            schema_version="2026-06-27.pr4",
        )
        comparison_out = comparison_root / "model_matrix.json"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    "comparison-only",
                    "--model-run",
                    f"model-a={report_a.as_posix()}",
                    "--model-run",
                    f"model-b={report_b.as_posix()}",
                    "--comparison-out",
                    comparison_out.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn("Model comparison:", stdout.getvalue())
        matrix = json.loads(comparison_out.read_text(encoding="utf-8"))
        self.assertEqual(matrix["comparison_status"], "comparable")
        self.assertEqual(matrix["scenario"], "datasource_documentation")
        self.assertEqual(matrix["pathway_id"], "datasource_documentation")
        self.assertEqual(matrix["report_schema_version"], "2026-06-27.pr4")
        self.assertEqual(
            [(row["label"], row["model"], row["overall_score_0_5"]) for row in matrix["runs"]],
            [("model-a", "model-a", 4.5), ("model-b", "model-b", 3.25)],
        )

    def test_collect_and_score_main_rejects_model_matrix_schema_drift(self) -> None:
        comparison_root = Path("tmp") / "blind-agentic-collect-score-test" / "comparison-drift"
        comparison_root.mkdir(parents=True, exist_ok=True)
        report_a = self._write_report_for_comparison(
            comparison_root / "model-a-report.json",
            run_id="model-a-run",
            model="model-a",
            score=4.5,
            schema_version="2026-06-27.pr4",
        )
        report_b = self._write_report_for_comparison(
            comparison_root / "model-b-report.json",
            run_id="model-b-run",
            model="model-b",
            score=3.25,
            schema_version="2026-06-27.pr3",
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    "comparison-drift",
                    "--model-run",
                    f"model-a={report_a.as_posix()}",
                    "--model-run",
                    f"model-b={report_b.as_posix()}",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("same report schema", stderr.getvalue())

    def _write_subject_outputs(self, subject_path: Path) -> None:
        generated = subject_path / ".elicit"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "diagnosis.md").write_text(
            "\n".join(
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
            ),
            encoding="utf-8",
        )

    def _write_graph_store(self, graph_db: Path) -> None:
        graph_db.parent.mkdir(parents=True, exist_ok=True)
        graph_db.unlink(missing_ok=True)
        with GraphStore(str(graph_db)) as store:
            store.create_graph("revops_graph", name="RevOps Growth")
            for node in [
                {"id": "mkt", "label": "MKT Campaigns", "type": "Data Source"},
                {"id": "crm", "label": "Customer Accounts", "type": "Data Source"},
                {"id": "billing", "label": "Subscription Billing", "type": "Data Source"},
                {"id": "finance", "label": "Revenue Ledger", "type": "Data Source"},
                {"id": "usage", "label": "Product Telemetry", "type": "Data Source"},
                {"id": "support", "label": "Support Cases", "type": "Data Source"},
                {"id": "pipeline", "label": "Marketing Influenced Pipeline", "type": "KPI"},
                {"id": "nrr", "label": "Net Revenue Retention", "type": "KPI"},
            ]:
                store.node_repo.upsert_node("revops_graph", {**node, "details": {}})
            for edge in [
                {"source": "mkt", "target": "pipeline", "label": "influences", "weight": 1.0},
                {"source": "crm", "target": "pipeline", "label": "depends_on", "weight": 1.0},
                {"source": "billing", "target": "nrr", "label": "depends_on", "weight": 1.0},
                {"source": "finance", "target": "nrr", "label": "measures", "weight": 1.0},
                {"source": "usage", "target": "nrr", "label": "uses", "weight": 1.0},
                {"source": "support", "target": "nrr", "label": "influences", "weight": 1.0},
            ]:
                store.edge_repo.upsert_edge("revops_graph", edge)
            questions: list[_PendingQuestion] = [
                {
                    "target_node_id": "mkt",
                    "gap_kind": "ownership",
                    "entity_type": "Data Source",
                    "question_text": "Who is the accountable source owner?",
                    "stakeholder_owner": "RevOps",
                },
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
            for question in questions:
                store.insert_pending_question("revops_graph", **question)

    def _write_report_for_comparison(
        self,
        path: Path,
        *,
        run_id: str,
        model: str,
        score: float,
        schema_version: str,
    ) -> Path:
        path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "scenario": "datasource_documentation",
                    "overall_score_0_5": score,
                    "deterministic": {"status": "passed"},
                    "freshness": {"report_schema_version": schema_version, "status": "passed"},
                    "trace_summary": {"model": model, "pathway_id": "datasource_documentation"},
                    "comparable_rerun_metadata": {
                        "prompt_version": "datasource-documentation-v1",
                        "fixture_version": "datasource-documentation-fixture-v1",
                        "rubric_version": "datasource-documentation-rubric-v1",
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path
