from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import TypedDict

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic.collect_evidence import collect_evidence
from tests.eval.blind_agentic.collect_and_score import build_model_comparison
from tests.eval.blind_agentic.prepare_subject import prepare_subject
from tests.eval.blind_agentic.score_report import score_evidence


class _PendingQuestion(TypedDict):
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str


class BlindAgenticFixtureLoopTests(unittest.TestCase):
    def test_prepare_collect_score_loop_without_opencode_has_stable_fields(self) -> None:
        run_id = "loop-run-001"
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-loop-test",
        )
        self._write_subject_outputs(workspace.subject_path)

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id=run_id,
            subject_path=workspace.subject_path,
            evidence_path=workspace.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )
        report = score_evidence(
            scenario="revops_growth",
            evidence_path=bundle.evidence_path,
            out_path=workspace.subject_path.parent / "report.json",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["run_id"], run_id)
        self.assertEqual(manifest["scenario"], "revops_growth")
        self.assertEqual(manifest["minimum_evidence"]["status"], "accepted")
        self.assertEqual(manifest["session_transcript"]["status"], "missing")
        self.assertEqual(manifest["run_metadata"]["prompt_version"], "revops-growth-v1")
        self.assertEqual(manifest["run_metadata"]["fixture_version"], "revops-growth-fixture-v1")

        self.assertEqual(report["run_id"], run_id)
        self.assertEqual(report["scenario"], "revops_growth")
        self.assertEqual(report["overall_score_0_5"], 5.0)
        self.assertEqual(report["anti_contamination"]["status"], "passed")
        self.assertEqual(report["comparable_rerun_metadata"]["prompt_version"], "revops-growth-v1")
        self.assertEqual(
            report["comparable_rerun_metadata"]["fixture_version"], "revops-growth-fixture-v1"
        )

    def test_model_comparison_requires_same_scenario_pathway_and_schema(self) -> None:
        report_a = {
            "run_id": "datasource-a",
            "scenario": "datasource_documentation",
            "overall_score_0_5": 4.75,
            "deterministic": {"status": "passed"},
            "freshness": {"report_schema_version": "2026-06-27.pr4", "status": "passed"},
            "trace_summary": {"model": "model-a", "pathway_id": "datasource_documentation"},
            "comparable_rerun_metadata": {
                "prompt_version": "datasource-documentation-v1",
                "fixture_version": "datasource-documentation-fixture-v1",
                "rubric_version": "datasource-documentation-rubric-v1",
            },
        }
        report_b = {
            **report_a,
            "run_id": "datasource-b",
            "overall_score_0_5": 4.0,
            "trace_summary": {"model": "model-b", "pathway_id": "datasource_documentation"},
        }

        comparison = build_model_comparison(
            scenario="datasource_documentation",
            model_runs=[("model-a", report_a), ("model-b", report_b)],
        )

        self.assertEqual(comparison["comparison_status"], "comparable")
        self.assertEqual(comparison["pathway_id"], "datasource_documentation")
        self.assertEqual(comparison["report_schema_version"], "2026-06-27.pr4")
        self.assertEqual(
            [run["deterministic_status"] for run in comparison["runs"]],
            ["passed", "passed"],
        )

    def _write_subject_outputs(self, subject_path: Path) -> None:
        brain_ds = subject_path / ".brain_ds"
        brain_ds.mkdir(parents=True, exist_ok=True)
        self._write_graph_store(brain_ds / "store.db")
        (brain_ds / "setup.json").write_text(
            json.dumps({"agents": ["opencode"], "workspace": "subject"}),
            encoding="utf-8",
        )

        generated = subject_path / "generated"
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
