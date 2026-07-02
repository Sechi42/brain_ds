from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.eval.blind_agentic.prepare_subject import (
    PrepareSubjectError,
    _build_sqlite_from_csv_sources,
    prepare_subject,
    scan_for_contamination,
    validate_non_goal_request,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class BlindAgenticPrepareTests(unittest.TestCase):
    def test_seeded_subject_workspace_contains_revops_sources_and_prompt(self) -> None:
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id="unit-run-001",
            output_root=self._tmp_root(),
        )

        files = {path.relative_to(workspace.subject_path).as_posix() for path in workspace.files}

        self.assertIn("README.md", files)
        self.assertIn("PROMPT.md", files)
        self.assertIn("seed_graph.json", files)
        self.assertIn("sources/revops.sqlite", files)
        self.assertIn("sources/crm_accounts.csv", files)
        self.assertIn("sources/marketing_campaigns.csv", files)
        self.assertIn("sources/billing_subscriptions.csv", files)
        self.assertIn("sources/product_usage.csv", files)
        self.assertIn("sources/support_tickets.csv", files)
        self.assertIn("sources/finance_revenue.csv", files)

        with sqlite3.connect(workspace.subject_path / "sources" / "revops.sqlite") as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            }

        self.assertEqual(
            tables,
            {
                "billing_subscriptions",
                "crm_accounts",
                "finance_revenue",
                "marketing_campaigns",
                "product_usage",
                "support_tickets",
            },
        )

    def test_prepare_subject_anchors_default_output_root_to_repo_root_from_tests_cwd(self) -> None:
        run_id = "unit-run-cwd-stable"
        run_root = REPO_ROOT / "tmp" / "blind-agentic-eval" / run_id
        wrong_run_root = REPO_ROOT / "tests" / "tmp" / "blind-agentic-eval" / run_id
        shutil.rmtree(run_root, ignore_errors=True)
        shutil.rmtree(wrong_run_root, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(run_root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(wrong_run_root, ignore_errors=True))

        previous_cwd = Path.cwd()
        os.chdir(REPO_ROOT / "tests")
        try:
            workspace = prepare_subject(scenario="revops_growth", run_id=run_id)
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(workspace.subject_path, run_root / "subject")
        self.assertTrue(workspace.subject_path.is_absolute())
        self.assertTrue((workspace.subject_path / "PROMPT.md").is_file())
        self.assertFalse((wrong_run_root / "subject").exists())

    def test_datasource_documentation_fixture_and_gold_contract_are_isolated(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-doc-001",
            output_root=self._tmp_root(),
        )

        files = {path.relative_to(workspace.subject_path).as_posix() for path in workspace.files}
        gold_root = Path(__file__).parent / "gold" / "blind_agentic" / "datasource_documentation"
        rubric = json.loads((gold_root / "rubric.json").read_text(encoding="utf-8"))
        gold = json.loads((gold_root / "gold_v2.json").read_text(encoding="utf-8"))

        self.assertIn("PROMPT.md", files)
        self.assertIn("seed_graph.json", files)
        self.assertIn("sources/source_catalog.csv", files)
        self.assertIn("sources/datasource.sqlite", files)
        self.assertNotIn("rubric.json", {Path(path).name for path in files})
        self.assertEqual(scan_for_contamination(workspace.subject_path), [])
        self.assertEqual(rubric["scenario"], "datasource_documentation")
        self.assertEqual(gold["pathway_id"], "datasource_documentation")
        self.assertEqual(
            [milestone["id"] for milestone in gold["pathway_milestones"]],
            ["orchestrator_entry", "explore_source", "document_source", "map_to_graph"],
        )

    def test_prepare_same_run_id_recreates_datasource_workspace_without_sqlite_lock(self) -> None:
        output_root = self._tmp_root()
        run_id = "datasource-rerun-recreate-001"

        first = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=output_root,
        )
        first_db = first.subject_path / "sources" / "datasource.sqlite"
        conn = sqlite3.connect(first_db)
        try:
            first_tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        finally:
            conn.close()

        second = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=output_root,
        )
        second_db = second.subject_path / "sources" / "datasource.sqlite"
        conn = sqlite3.connect(second_db)
        try:
            second_tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual(second.subject_path, first.subject_path)
        self.assertTrue(second_db.is_file())
        self.assertEqual(second_tables, first_tables)

    def test_datasource_subject_metadata_stamps_blind_flow_protocol_version(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-protocol-metadata-001",
            output_root=self._tmp_root(),
        )

        protocol = json.loads(
            (workspace.subject_path / ".brain_ds" / "setup.json").read_text(encoding="utf-8")
        )["blind_agentic_protocol"]

        self.assertEqual(protocol["version"], "blind-agent-flow-v1")
        self.assertEqual(protocol["required_orchestrator"], "brain-ds-orchestrator")
        self.assertEqual(protocol["prompt_path"], "PROMPT.md")
        self.assertIn("generated/source_documentation.md", protocol["expected_outputs"])
        self.assertEqual(protocol["graph_db"], ".brain_ds/store.db")
        self.assertEqual(protocol["opencode_export"], "opencode-export/session.json")
        self.assertEqual(
            protocol["wrapper_diagnostics"],
            [
                "diagnostics/opencode-run.stdout.jsonl",
                "diagnostics/opencode-run.stderr.txt",
                "diagnostics/opencode-export.stderr.txt",
            ],
        )
        self.assertIn("opencode_export", protocol["required_evidence"])
        self.assertIn("workspace_open_before_graph_write", protocol["required_evidence"])

    def test_slice2_path_fixtures_and_gold_are_isolated_and_subject_ready(self) -> None:
        cases = {
            "kpi_lineage": {
                "pathway_id": "kpi_lineage",
                "sqlite": "kpi_lineage.sqlite",
                "source": "sources/kpi_targets.csv",
            },
            "currency_elicitation": {
                "pathway_id": "currency_elicitation",
                "sqlite": "currency_elicitation.sqlite",
                "source": "sources/stakeholder_signals.csv",
            },
        }

        for scenario, expected in cases.items():
            with self.subTest(scenario=scenario):
                workspace = prepare_subject(
                    scenario=scenario,
                    run_id=f"{scenario}-001",
                    output_root=self._tmp_root(),
                )
                files = {path.relative_to(workspace.subject_path).as_posix() for path in workspace.files}
                gold_root = Path(__file__).parent / "gold" / "blind_agentic" / scenario
                gold = json.loads((gold_root / "gold_v2.json").read_text(encoding="utf-8"))

                self.assertIn("PROMPT.md", files)
                self.assertIn("seed_graph.json", files)
                self.assertIn(expected["source"], files)
                self.assertIn(f"sources/{expected['sqlite']}", files)
                self.assertEqual(gold["scenario"], scenario)
                self.assertEqual(gold["pathway_id"], expected["pathway_id"])
                self.assertNotIn("rubric.json", {Path(path).name for path in files})
                self.assertEqual(scan_for_contamination(workspace.subject_path), [])

    def test_evaluator_only_files_are_not_copied_to_subject_workspace(self) -> None:
        workspace = prepare_subject(
            scenario="revops_growth",
            run_id="unit-run-002",
            output_root=self._tmp_root(),
        )

        subject_files = [
            path.name.lower() for path in workspace.subject_path.rglob("*") if path.is_file()
        ]

        self.assertNotIn("rubric.json", subject_files)
        self.assertNotIn("gold_graph.json", subject_files)
        self.assertFalse(any("expected" in name for name in subject_files))
        self.assertEqual(scan_for_contamination(workspace.subject_path), [])

    def test_contamination_scan_reports_subject_visible_forbidden_terms(self) -> None:
        subject = Path(tempfile.mkdtemp(prefix="blind-agentic-contamination-")) / "subject"
        subject.mkdir(parents=True)
        (subject / "notes.md").write_text(
            "Use the answer key before writing outputs.", encoding="utf-8"
        )

        findings = scan_for_contamination(subject)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["term"], "answer key")
        self.assertEqual(findings[0]["path"], "notes.md")

    def test_forbidden_execution_paths_are_rejected(self) -> None:
        cases = [
            ({"requires_local_model": True}, "local model"),
            ({"requires_openai_api_key": True}, "OpenAI"),
            ({"requires_opencode_go_api_key": True}, "opencode-go"),
            ({"requires_live_llm_ci_gate": True}, "live-LLM CI"),
            ({"requires_ci_live_llm_gate": True}, "live-LLM CI"),
            ({"requires_pyagent_replatforming": True}, "PyAgent"),
        ]

        for options, message in cases:
            with self.subTest(options=options):
                with self.assertRaisesRegex(PrepareSubjectError, message):
                    validate_non_goal_request(options)

    def test_non_goal_guard_accepts_manual_membership_offline_scoring_path(self) -> None:
        validate_non_goal_request(
            {
                "uses_opencode_membership_session": True,
                "scores_offline": True,
                "requires_local_model": False,
                "requires_openai_api_key": False,
                "requires_opencode_go_api_key": False,
                "requires_live_llm_ci_gate": False,
                "requires_pyagent_replatforming": False,
            }
        )

    def test_hidden_evaluator_bundle_has_required_gold_and_rubric(self) -> None:
        gold_root = Path(__file__).parent / "gold" / "blind_agentic" / "revops_growth"

        rubric = json.loads((gold_root / "rubric.json").read_text(encoding="utf-8"))
        gold_graph = json.loads((gold_root / "gold_graph.json").read_text(encoding="utf-8"))
        lineage = json.loads((gold_root / "expected_kpi_lineage.json").read_text(encoding="utf-8"))
        contamination = json.loads(
            (gold_root / "contamination_terms.json").read_text(encoding="utf-8")
        )

        self.assertEqual(rubric["scenario"], "revops_growth")
        self.assertGreater(rubric["axes"]["lineage_correctness"]["weight"], 0.3)
        self.assertGreaterEqual(len(gold_graph["nodes"]), 6)
        self.assertIn("net_revenue_retention", lineage["kpis"])
        self.assertIn("answer key", contamination["forbidden_terms"])

    def test_documented_cli_command_creates_default_subject_workspace(self) -> None:
        run_id = "unit-cli-prepare-001"
        run_root = Path("tmp") / "blind-agentic-eval" / run_id
        shutil.rmtree(run_root, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(run_root, ignore_errors=True))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.prepare_subject",
                "--scenario",
                "revops_growth",
                "--run-id",
                run_id,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        subject_path = run_root / "subject"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(subject_path.is_dir())
        self.assertTrue((subject_path / "PROMPT.md").is_file())
        self.assertTrue((subject_path / "sources" / "revops.sqlite").is_file())
        self.assertIn(subject_path.as_posix(), result.stdout)
        self.assertIn("OpenCode", result.stdout)

    def test_cli_reports_unknown_scenario_as_error(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.prepare_subject",
                "--scenario",
                "missing_scenario",
                "--run-id",
                "unit-cli-prepare-missing",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown blind subject scenario: missing_scenario", result.stderr)

    def test_csv_identifiers_are_quoted_for_sqlite_table_and_column_names(self) -> None:
        sources = self._tmp_root() / "quoted-identifiers"
        sources.mkdir(parents=True, exist_ok=True)
        (sources / "weird table name.csv").write_text(
            'select,"quoted column",two words\nvalue,"quoted",space\n',
            encoding="utf-8",
        )

        _build_sqlite_from_csv_sources(sources, sqlite_name="quoted.sqlite")

        with sqlite3.connect(sources / "quoted.sqlite") as conn:
            rows = conn.execute(
                'SELECT "select", "quoted column", "two words" FROM "weird table name"'
            ).fetchall()

        self.assertEqual(rows, [("value", "quoted", "space")])

    def test_csv_identifiers_reject_nul_bytes(self) -> None:
        sources = self._tmp_root() / "invalid-identifiers"
        sources.mkdir(parents=True, exist_ok=True)
        (sources / "invalid.csv").write_text("good,bad\x00name\n1,2\n", encoding="utf-8")

        with self.assertRaisesRegex(PrepareSubjectError, "NUL"):
            _build_sqlite_from_csv_sources(sources, sqlite_name="invalid.sqlite")

    def _tmp_root(self) -> Path:
        root = Path("tmp") / "blind-agentic-eval-test"
        root.mkdir(parents=True, exist_ok=True)
        return root
