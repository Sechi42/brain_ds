from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Sequence, TypedDict

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic import collect_and_score
from tests.eval.blind_agentic.prepare_subject import prepare_subject
from tests.eval.blind_agentic.trace_schema import _parse_opencode_stderr


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

    def test_collect_and_score_main_returns_invalid_for_fallback_build_agent_trace(self) -> None:
        run_id = "collect-score-build-agent-invalid"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T01:37:37.942Z level=INFO message=stream session.id=ses_build agent=build mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps({"type": "text", "timestamp": 1782697085951, "sessionID": "ses_build", "part": {"type": "text", "text": "I can document this datasource."}}) + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("wrong_agent", stderr.getvalue())
        report_path = workspace.subject_path.parent / "report.json"
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["deterministic"]["status"], "fail")

    def test_collect_and_score_cli_rejects_legacy_diagnostics_without_canonical_export(
        self,
    ) -> None:
        run_id = "collect-score-legacy-diagnostics-no-export"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T01:37:37.942Z level=INFO "
            "message=stream session.id=ses_legacy agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782697085951,
                    "sessionID": "ses_legacy",
                    "part": {
                        "type": "text",
                        "text": "I can document this datasource.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.eval.blind_agentic.collect_and_score",
                "--scenario",
                "datasource_documentation",
                "--run-id",
                run_id,
                "--subject-path",
                workspace.subject_path.as_posix(),
                "--repo-root",
                Path.cwd().as_posix(),
                "--opencode-artifacts-path",
                opencode_dir.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual("", result.stdout)
        self.assertIn("Missing required OpenCode export", result.stderr)
        self.assertIn("opencode-export/session.json", result.stderr)
        self.assertIn("stdout/stderr diagnostics are not scoring evidence", result.stderr)

    def test_collect_and_score_main_accepts_delegated_child_created_before_parent_stream(
        self,
    ) -> None:
        run_id = "collect-score-created-child-before-parent"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_late_stream"
        subagent_session = "ses_subagent_created_first"
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    f"parentID={orchestrator_session} title=\"Run mapper (@brainds-connection-mapper subagent)\"",
                    "agent=brainds-connection-mapper model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-connection-mapper mode=subagent",
                    f"timestamp=2026-06-29T03:45:23.369Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": orchestrator_session,
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": orchestrator_session,
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702340123,
                            "sessionID": subagent_session,
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_explore_source",
                                "state": {
                                    "status": "completed",
                                    "input": {"node_id": "source-1"},
                                    "output": "source documented",
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn("Score report:", stdout.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "passed")
        self.assertNotIn(
            "orchestrator_bypass",
            {item.get("code") for item in report["blocking_failures"]},
        )
        self.assertEqual(
            report["trace_summary"]["first_root_brainds_agent"],
            "brain-ds-orchestrator",
        )

    def test_collect_and_score_main_rejects_child_created_first_without_parent_link(
        self,
    ) -> None:
        run_id = "collect-score-created-child-without-parent"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_late_unlinked"
        subagent_session = "ses_subagent_unlinked_first"
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    "agent=brainds-connection-mapper model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-connection-mapper mode=subagent",
                    f"timestamp=2026-06-29T03:45:23.369Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702339725,
                    "sessionID": orchestrator_session,
                    "part": {"type": "text", "text": "I will document this datasource."},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("orchestrator_bypass", stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            report["trace_summary"]["undelegated_subagent_contacts"][0]["agent_name"],
            "brainds-connection-mapper",
        )

    def test_collect_and_score_main_rejects_created_and_stream_only_subagent_proof(
        self,
    ) -> None:
        run_id = "collect-score-created-stream-only-subagent"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_stream_only"
        subagent_session = "ses_subagent_stream_only"
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    f"parentID={orchestrator_session} title=\"Run mapper (@brainds-connection-mapper subagent)\"",
                    "agent=brainds-connection-mapper model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-connection-mapper mode=subagent",
                    f"timestamp=2026-06-29T03:45:23.369Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": orchestrator_session,
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": orchestrator_session,
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("missing_subagent_action", stderr.getvalue())

    def test_collect_and_score_main_accepts_attributable_subagent_tool_proof(
        self,
    ) -> None:
        run_id = "collect-score-attributable-subagent-tool"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_tool_proof"
        subagent_session = "ses_subagent_tool_proof"
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    f"parentID={orchestrator_session} title=\"Run explorer (@brainds-source-explorer subagent)\"",
                    "agent=brainds-source-explorer model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-source-explorer mode=subagent",
                    f"timestamp=2026-06-29T03:45:23.369Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": orchestrator_session,
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": orchestrator_session,
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702340123,
                            "sessionID": subagent_session,
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_explore_source",
                                "state": {
                                    "status": "completed",
                                    "input": {"node_id": "source-1"},
                                    "output": "source documented",
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["trace_summary"]["subagent_action"]["status"], "verified")

    def test_collect_and_score_main_accepts_completed_task_result_as_subagent_proof(
        self,
    ) -> None:
        run_id = "collect-score-completed-task-result-proof"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        orchestrator_session = "ses_orchestrator_task_result"
        self._write_export_records(
            workspace.subject_path,
            [
                self._prompt_read_record(orchestrator_session, workspace.subject_path, sequence=1),
                self._orchestrator_text_record(orchestrator_session, sequence=2),
                self._open_workspace_record(orchestrator_session, workspace.subject_path, sequence=3),
                self._task_record(
                    orchestrator_session,
                    sequence=4,
                    subagent_type="brainds-source-explorer",
                    output="<task id=\"ses_child\" state=\"completed\"><task_result>Read CSV files and produced source documentation findings.</task_result></task>",
                ),
                self._graph_write_record(orchestrator_session, sequence=5),
            ],
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id=run_id,
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Score report:", stdout)
        report = json.loads((workspace.subject_path.parent / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["trace_summary"]["subagent_action"]["status"], "verified")
        self.assertEqual(report["trace_summary"]["subagent_action"]["task_result_count"], 1)

    def test_collect_and_score_main_rejects_bare_task_delegation_as_subagent_proof(
        self,
    ) -> None:
        run_id = "collect-score-bare-task-delegation"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        orchestrator_session = "ses_orchestrator_bare_task"
        self._write_export_records(
            workspace.subject_path,
            [
                self._prompt_read_record(orchestrator_session, workspace.subject_path, sequence=1),
                self._orchestrator_text_record(orchestrator_session, sequence=2),
                self._open_workspace_record(orchestrator_session, workspace.subject_path, sequence=3),
                self._task_record(
                    orchestrator_session,
                    sequence=4,
                    subagent_type="brainds-source-explorer",
                    output=None,
                ),
                self._graph_write_record(orchestrator_session, sequence=5),
            ],
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id=run_id,
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_subagent_action", stderr)

    def test_collect_and_score_main_rejects_missing_workspace_open_gate(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-missing-open-workspace",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(workspace.subject_path, include_open_workspace=False)

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-missing-open-workspace",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_workspace_open", stderr)
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["blocking_failures"][0]["code"], "missing_workspace_open")

    def test_collect_and_score_main_accepts_active_workspace_listing_before_graph_write(
        self,
    ) -> None:
        run_id = "collect-score-active-workspace-listing"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        orchestrator_session = "ses_orchestrator_active_listing"
        subagent_session = "ses_subagent_active_listing"
        self._write_export_records(
            workspace.subject_path,
            [
                self._prompt_read_record(orchestrator_session, workspace.subject_path, sequence=1),
                self._orchestrator_text_record(orchestrator_session, sequence=2),
                self._workspace_listing_record(orchestrator_session, workspace.subject_path, sequence=3),
                {
                    "type": "opencode_session",
                    "timestamp": 1782702339500,
                    "sequence": 4,
                    "sessionID": subagent_session,
                    "agent_name": "brainds-source-explorer",
                    "parent_session_id": orchestrator_session,
                },
                self._graph_write_record(subagent_session, sequence=5, agent_name="brainds-source-explorer"),
            ],
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id=run_id,
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Score report:", stdout)
        manifest = json.loads(
            (workspace.subject_path.parent / "evidence" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["workspace_open_gate"]["status"], "passed")
        self.assertIn("brain_ds_list_workspaces", manifest["workspace_open_gate"]["open_event_ref"])

    def test_collect_and_score_main_rejects_active_listing_without_active_workspace_entry(
        self,
    ) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-listing-no-active-entry",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_export_records(
            workspace.subject_path,
            self._workspace_listing_export_records(
                workspace.subject_path,
                listing_payload={
                    "active_project_root": workspace.subject_path.as_posix(),
                    "active_registered": True,
                    "workspaces": [{"path": workspace.subject_path.as_posix()}],
                },
            ),
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-listing-no-active-entry",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_workspace_open", stderr)

    def test_collect_and_score_main_rejects_active_listing_for_unrelated_workspace(
        self,
    ) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-listing-unrelated-active",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        unrelated = workspace.subject_path.parent / "unrelated-workspace"
        self._write_export_records(
            workspace.subject_path,
            self._workspace_listing_export_records(
                workspace.subject_path,
                listing_payload={
                    "active_project_root": workspace.subject_path.as_posix(),
                    "active_registered": True,
                    "workspaces": [{"path": unrelated.as_posix(), "active": True}],
                },
            ),
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-listing-unrelated-active",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_workspace_open", stderr)

    def test_collect_and_score_main_rejects_stale_active_workspace_listing(
        self,
    ) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-listing-stale-active",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        stale_workspace = workspace.subject_path.parent / "stale-workspace"
        self._write_export_records(
            workspace.subject_path,
            self._workspace_listing_export_records(
                workspace.subject_path,
                listing_payload={
                    "active_project_root": stale_workspace.as_posix(),
                    "active_registered": True,
                    "workspaces": [
                        {"path": workspace.subject_path.as_posix(), "active": False},
                        {"path": stale_workspace.as_posix(), "active": True},
                    ],
                },
            ),
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-listing-stale-active",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_workspace_open", stderr)

    def test_collect_and_score_main_rejects_graph_write_before_workspace_open(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-write-before-open",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(workspace.subject_path, write_before_open=True)

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-write-before-open",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("write_before_workspace_open", stderr)
        manifest = json.loads(
            (workspace.subject_path.parent / "evidence" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(manifest["workspace_open_gate"]["opened_before_write"])

    def test_collect_and_score_main_rejects_failed_workspace_open_before_graph_write(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-failed-open-workspace",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(
            workspace.subject_path,
            open_workspace_status="error",
            open_workspace_error="Workspace not registered",
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-failed-open-workspace",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("workspace_open_failed", stderr)
        manifest = json.loads(
            (workspace.subject_path.parent / "evidence" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["workspace_open_gate"]["status"], "failed")
        self.assertFalse(manifest["workspace_open_gate"]["opened_before_write"])

    def test_collect_and_score_main_accepts_successful_workspace_open_after_failed_retry(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-open-retry-success",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(workspace.subject_path, failed_open_before_success=True)

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-open-retry-success",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("Score report:", stdout)
        report = json.loads((workspace.subject_path.parent / "report.json").read_text(encoding="utf-8"))
        self.assertNotIn("workspace_open_failed", {item["code"] for item in report["blocking_failures"]})
        manifest = json.loads((workspace.subject_path.parent / "evidence" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["workspace_open_gate"]["status"], "passed")

    def test_collect_and_score_main_rejects_stale_subject_graph_proof(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-stale-subject-graph",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(workspace.subject_path)
        old_time = 1_700_000_000
        graph_db = workspace.subject_path / ".brain_ds" / "store.db"
        os.utime(graph_db, (old_time, old_time))
        (workspace.subject_path / "generated" / "source_documentation.md").touch()

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-stale-subject-graph",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("stale_graph_proof", stderr)

    def test_collect_and_score_main_rejects_non_subject_local_graph_proof(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-non-subject-graph",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        self._write_datasource_export(workspace.subject_path)
        external_workspace = workspace.subject_path.parent / "external-workspace"
        self._write_datasource_subject_outputs(external_workspace)

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-non-subject-graph",
            subject_path=workspace.subject_path,
            graph_db_path=external_workspace / ".brain_ds" / "store.db",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("non_subject_local_graph_proof", stderr)

    def test_collect_and_score_main_rejects_workspace_open_for_wrong_subject(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-wrong-open-workspace",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        wrong_workspace = workspace.subject_path.parent / "wrong-subject"
        self._write_datasource_export(
            workspace.subject_path,
            open_workspace_path=wrong_workspace,
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-wrong-open-workspace",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("wrong_workspace_open", stderr)
        manifest = json.loads(
            (workspace.subject_path.parent / "evidence" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["workspace_open_gate"]["opened_path"], wrong_workspace.as_posix())

    def test_collect_and_score_main_rejects_missing_source_documentation_file(self) -> None:
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-score-missing-source-doc",
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        (workspace.subject_path / "generated" / "source_documentation.md").unlink()
        self._write_datasource_export(workspace.subject_path)

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id="collect-score-missing-source-doc",
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_generated_source_documentation", stderr)

    def test_collect_and_score_main_accepts_delegated_subagent_text_work(self) -> None:
        run_id = "collect-score-delegated-subagent-text-work"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_text_proof"
        subagent_session = "ses_subagent_text_proof"
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    f"parentID={orchestrator_session} title=\"Run writer (@brainds-source-explorer subagent)\"",
                    "agent=brainds-source-explorer model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-source-explorer mode=subagent",
                    f"timestamp=2026-06-29T03:45:23.369Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": orchestrator_session,
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": orchestrator_session,
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702340123,
                            "sessionID": subagent_session,
                            "part": {
                                "type": "text",
                                "text": "Source documentation drafted with owners and freshness notes.",
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["trace_summary"]["subagent_action"]["status"], "verified")
        self.assertEqual(report["trace_summary"]["subagent_action"]["action_count"], 1)

    def test_collect_and_score_main_rejects_task_delegation_without_subagent_proof(self) -> None:
        run_id = "collect-score-task-only-subagent-proof"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        orchestrator_session = "ses_orchestrator_task_only"
        export_path = workspace.subject_path.parent / "opencode-export" / "session.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sequence": 1,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": (workspace.subject_path / "PROMPT.md").as_posix()},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        },
                        {
                            "type": "text",
                            "timestamp": 1782702339100,
                            "sequence": 2,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "I will delegate source documentation."},
                        },
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339300,
                            "sequence": 3,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_open_workspace",
                                "state": {"status": "completed", "input": {"path": workspace.subject_path.as_posix()}},
                            },
                        },
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339400,
                            "sequence": 4,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "task",
                                "state": {
                                    "status": "completed",
                                    "input": {"subagent_type": "brainds-source-explorer"},
                                    "output": "Delegation accepted.",
                                },
                            },
                        },
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339500,
                            "sequence": 5,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_update_node",
                                "state": {"status": "completed", "input": {"graph_id": "helios-datasource-docs"}},
                            },
                        },
                    ]
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        exit_code, stdout, stderr = self._run_datasource_collect_and_score(
            run_id=run_id,
            subject_path=workspace.subject_path,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual("", stdout)
        self.assertIn("missing_subagent_action", stderr)
        report = json.loads((workspace.subject_path.parent / "report.json").read_text(encoding="utf-8"))
        subagent_action = report["trace_summary"]["subagent_action"]
        self.assertEqual(subagent_action["status"], "missing")
        self.assertEqual(subagent_action["subagents"], ["brainds-source-explorer"])
        self.assertEqual(subagent_action["action_count"], 0)

    def test_collect_and_score_main_scores_root_agent_by_event_chronology(
        self,
    ) -> None:
        run_id = "collect-score-root-agent-chronology"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_chronology"
        subagent_session = "ses_subagent_chronology"
        (opencode_dir / "opencode-stdout-a-later-subagent.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702340000,
                            "sessionID": subagent_session,
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brain-ds-orchestrator",
                            "part": {
                                "type": "text",
                                "text": "I am exploring the source as the delegated subagent.",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702340123,
                            "sessionID": subagent_session,
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_explore_source",
                                "state": {
                                    "status": "completed",
                                    "input": {"node_id": "source-1"},
                                    "output": "source documented",
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-z-earlier-orchestrator.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            report["trace_summary"]["first_root_brainds_agent"],
            "brain-ds-orchestrator",
        )
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "passed")

    def test_collect_and_score_main_uses_sequence_to_break_equal_timestamp_root_agent_ties(
        self,
    ) -> None:
        run_id = "collect-score-root-agent-equal-timestamp-sequence"
        workspace = prepare_subject(
            scenario="datasource_documentation",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-collect-score-test",
        )
        self._write_datasource_subject_outputs(workspace.subject_path)
        opencode_dir = workspace.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        orchestrator_session = "ses_orchestrator_sequence"
        subagent_session = "ses_subagent_sequence"
        shared_timestamp = 1782702340000
        (opencode_dir / "opencode-stdout-a-subagent.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": shared_timestamp,
                            "sequence": 3,
                            "sessionID": subagent_session,
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brain-ds-orchestrator",
                            "part": {
                                "type": "text",
                                "text": "I am exploring the source as the delegated subagent.",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": shared_timestamp,
                            "sequence": 4,
                            "sessionID": subagent_session,
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_explore_source",
                                "state": {
                                    "status": "completed",
                                    "input": {"node_id": "source-1"},
                                    "output": "source documented",
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-z-orchestrator.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": shared_timestamp,
                            "sequence": 1,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": shared_timestamp,
                            "sequence": 2,
                            "sessionID": orchestrator_session,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_canonical_export_from_legacy(workspace.subject_path, opencode_dir)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--subject-path",
                    workspace.subject_path.as_posix(),
                    "--repo-root",
                    Path.cwd().as_posix(),
                    "--opencode-artifacts-path",
                    opencode_dir.as_posix(),
                ]
            )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        report = json.loads(
            (workspace.subject_path.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            report["trace_summary"]["first_root_brainds_agent"],
            "brain-ds-orchestrator",
        )
        self.assertEqual(report["deterministic"]["orchestrator_gate"]["status"], "passed")

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

    def _write_datasource_subject_outputs(self, subject_path: Path) -> None:
        generated = subject_path / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "source_documentation.md").write_text(
            "# Source Documentation\n\nOrders has owner, freshness, and data gaps documented.",
            encoding="utf-8",
        )
        graph_db = subject_path / ".brain_ds" / "store.db"
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
                {"source": "source-orders", "target": "source-customers", "label": "uses", "weight": 1.0},
            )

    def _write_datasource_export(
        self,
        subject_path: Path,
        *,
        include_open_workspace: bool = True,
        write_before_open: bool = False,
        open_workspace_path: Path | None = None,
        open_workspace_status: str = "completed",
        open_workspace_error: str | None = None,
        failed_open_before_success: bool = False,
    ) -> Path:
        orchestrator_session = "ses_orchestrator_workspace_gate"
        subagent_session = "ses_subagent_workspace_gate"
        open_workspace = {
            "type": "tool_use",
            "timestamp": 1782702339300,
            "sequence": 3,
            "sessionID": orchestrator_session,
            "agent_name": "brain-ds-orchestrator",
            "part": {
                "type": "tool",
                "tool": "brain_ds_open_workspace",
                "state": {
                    "status": open_workspace_status,
                    "input": {"path": (open_workspace_path or subject_path).as_posix()},
                    **({"error": open_workspace_error} if open_workspace_error else {}),
                },
            },
        }
        graph_write = {
            "type": "tool_use",
            "timestamp": 1782702339200 if write_before_open else 1782702340200,
            "sequence": 2 if write_before_open else 8,
            "sessionID": subagent_session,
            "agent_name": "brainds-source-explorer",
            "delegated_by": "brain-ds-orchestrator",
            "part": {
                "type": "tool",
                "tool": "brain_ds_update_node",
                "state": {"status": "completed", "input": {"graph_id": "helios-datasource-docs"}},
            },
        }
        records: list[object] = [
            {
                "type": "opencode_session",
                "timestamp": 1782702338000,
                "sequence": 0,
                "sessionID": subagent_session,
                "agent_name": "brainds-source-explorer",
                "parent_session_id": orchestrator_session,
            },
            {
                "type": "tool_use",
                "timestamp": 1782702339008,
                "sequence": 1,
                "sessionID": orchestrator_session,
                "agent_name": "brain-ds-orchestrator",
                "part": {
                    "type": "tool",
                    "tool": "read",
                    "state": {
                        "status": "completed",
                        "input": {"filePath": (subject_path / "PROMPT.md").as_posix()},
                        "output": "1: Document the Helios datasource.",
                    },
                },
            },
            {
                "type": "text",
                "timestamp": 1782702339100,
                "sequence": 2,
                "sessionID": orchestrator_session,
                "agent_name": "brain-ds-orchestrator",
                "part": {"type": "text", "text": "I will document this datasource."},
            },
            graph_write,
            {
                "type": "tool_use",
                "timestamp": 1782702340300,
                "sequence": 9,
                "sessionID": subagent_session,
                "agent_name": "brainds-source-explorer",
                "delegated_by": "brain-ds-orchestrator",
                "part": {
                    "type": "tool",
                    "tool": "brain_ds_explore_source",
                    "state": {"status": "completed", "input": {"node_id": "source-orders"}},
                },
            },
        ]
        if failed_open_before_success:
            failed_open = dict(open_workspace)
            failed_open["sequence"] = 3
            failed_open["timestamp"] = 1782702339200
            failed_open["part"] = {
                "type": "tool",
                "tool": "brain_ds_open_workspace",
                "state": {
                    "status": "error",
                    "input": {"path": "relative/subject"},
                    "error": "Workspace not registered",
                },
            }
            records.append(failed_open)
        if include_open_workspace:
            records.append(open_workspace)
        export_path = subject_path.parent / "opencode-export" / "session.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps({"records": records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return export_path

    def _write_export_records(self, subject_path: Path, records: Sequence[object]) -> Path:
        export_path = subject_path.parent / "opencode-export" / "session.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps({"records": records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return export_path

    def _prompt_read_record(self, session_id: str, subject_path: Path, *, sequence: int) -> dict[str, object]:
        return {
            "type": "tool_use",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": "brain-ds-orchestrator",
            "part": {
                "type": "tool",
                "tool": "read",
                "state": {
                    "status": "completed",
                    "input": {"filePath": (subject_path / "PROMPT.md").as_posix()},
                    "output": "1: Document the Helios datasource.",
                },
            },
        }

    def _orchestrator_text_record(self, session_id: str, *, sequence: int) -> dict[str, object]:
        return {
            "type": "text",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": "brain-ds-orchestrator",
            "part": {"type": "text", "text": "I will document this datasource."},
        }

    def _open_workspace_record(
        self, session_id: str, subject_path: Path, *, sequence: int
    ) -> dict[str, object]:
        return {
            "type": "tool_use",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": "brain-ds-orchestrator",
            "part": {
                "type": "tool",
                "tool": "brain_ds_open_workspace",
                "state": {"status": "completed", "input": {"path": subject_path.as_posix()}},
            },
        }

    def _workspace_listing_record(
        self,
        session_id: str,
        subject_path: Path,
        *,
        sequence: int,
        listing_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = listing_payload or {
            "active_project_root": subject_path.as_posix(),
            "active_registered": True,
            "workspaces": [{"path": subject_path.as_posix(), "active": True}],
        }
        return {
            "type": "tool_use",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": "brain-ds-orchestrator",
            "part": {
                "type": "tool",
                "tool": "brain_ds_list_workspaces",
                "state": {
                    "status": "completed",
                    "input": {},
                    "output": json.dumps(payload),
                },
            },
        }

    def _workspace_listing_export_records(
        self,
        subject_path: Path,
        *,
        listing_payload: dict[str, object],
    ) -> list[dict[str, object]]:
        orchestrator_session = "ses_orchestrator_active_listing"
        subagent_session = "ses_subagent_active_listing"
        return [
            self._prompt_read_record(orchestrator_session, subject_path, sequence=1),
            self._orchestrator_text_record(orchestrator_session, sequence=2),
            self._workspace_listing_record(
                orchestrator_session,
                subject_path,
                sequence=3,
                listing_payload=listing_payload,
            ),
            {
                "type": "opencode_session",
                "timestamp": 1782702339500,
                "sequence": 4,
                "sessionID": subagent_session,
                "agent_name": "brainds-source-explorer",
                "parent_session_id": orchestrator_session,
            },
            self._graph_write_record(subagent_session, sequence=5, agent_name="brainds-source-explorer"),
        ]

    def _task_record(
        self, session_id: str, *, sequence: int, subagent_type: str, output: str | None
    ) -> dict[str, object]:
        state: dict[str, object] = {
            "status": "completed" if output is not None else "pending",
            "input": {"subagent_type": subagent_type, "description": "Document sources"},
        }
        if output is not None:
            state["output"] = output
        return {
            "type": "tool_use",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": "brain-ds-orchestrator",
            "part": {"type": "tool", "tool": "task", "state": state},
        }

    def _graph_write_record(
        self,
        session_id: str,
        *,
        sequence: int,
        agent_name: str = "brain-ds-orchestrator",
    ) -> dict[str, object]:
        return {
            "type": "tool_use",
            "timestamp": 1782702339000 + sequence,
            "sequence": sequence,
            "sessionID": session_id,
            "agent_name": agent_name,
            "part": {
                "type": "tool",
                "tool": "brain_ds_update_node",
                "state": {"status": "completed", "input": {"graph_id": "helios-datasource-docs"}},
            },
        }

    def _run_datasource_collect_and_score(
        self, *, run_id: str, subject_path: Path, graph_db_path: Path | None = None
    ) -> tuple[int, str, str]:
        args = [
            "--scenario",
            "datasource_documentation",
            "--run-id",
            run_id,
            "--subject-path",
            subject_path.as_posix(),
            "--repo-root",
            Path.cwd().as_posix(),
        ]
        if graph_db_path is not None:
            args.extend(["--graph-db-path", graph_db_path.as_posix()])
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = collect_and_score.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _write_canonical_export_from_legacy(
        self, subject_path: Path, opencode_artifacts_path: Path
    ) -> Path:
        records: list[object] = []
        for source in sorted(opencode_artifacts_path.rglob("*")):
            if not source.is_file():
                continue
            name = source.name.lower()
            if source.suffix.lower() == ".log" and name.startswith("opencode") and "stderr" in name:
                records.extend(_parse_opencode_stderr(source, root=opencode_artifacts_path))
                continue
            if source.suffix.lower() not in {".jsonl", ".ndjson"} or not name.startswith(
                "opencode-stdout"
            ):
                continue
            for line in source.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        export_path = subject_path.parent / "opencode-export" / "session.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps({"records": records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return export_path

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
