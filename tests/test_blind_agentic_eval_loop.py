from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from typing import TypedDict

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic.collect_evidence import collect_evidence
from tests.eval.blind_agentic.collect_and_score import build_model_comparison
from tests.eval.blind_agentic.prepare_subject import prepare_subject
from tests.eval.blind_agentic.run_opencode_verifier import (
    OpenCodeVerifierError,
    build_opencode_run_command,
    main as opencode_verifier_main,
    run_verifier,
)
from tests.eval.blind_agentic.score_report import score_evidence


class _PendingQuestion(TypedDict):
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str


class BlindAgenticFixtureLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._opencode_which = patch(
            "tests.eval.blind_agentic.run_opencode_verifier.shutil.which",
            return_value=None,
        )
        self._opencode_which.start()

    def tearDown(self) -> None:
        self._opencode_which.stop()

    def test_opencode_verifier_builds_required_orchestrator_command(self) -> None:
        command = build_opencode_run_command(Path("/tmp/subject"), model="opencode/test-model")

        self.assertEqual(command[:6], ["opencode", "run", "--agent", "brain-ds-orchestrator", "--format", "json"])
        self.assertEqual(command[-4:], ["--dir", "/tmp/subject", "--model", "opencode/test-model"])

    def test_opencode_verifier_rejects_wrong_orchestrator(self) -> None:
        with self.assertRaisesRegex(OpenCodeVerifierError, "wrong-agent"):
            build_opencode_run_command(Path("/tmp/subject"), agent="general")

    def test_opencode_verifier_fails_fast_without_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=0, stdout=json.dumps({"message": "ok"}), stderr=""
                )

                with self.assertRaisesRegex(OpenCodeVerifierError, "missing-sessionID"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="missing-session",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

                self.assertEqual(run_mock.call_count, 1)

    def test_opencode_verifier_fails_fast_on_export_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"], returncode=0, stdout=json.dumps({"sessionID": "ses_123"}), stderr=""
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_123"], returncode=1, stdout="", stderr="no export"
                    ),
                ]

                with self.assertRaisesRegex(OpenCodeVerifierError, "export-failed"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="export-failure",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

                self.assertEqual(run_mock.call_count, 2)
                self.assertEqual(run_mock.call_args_list[1].args[0], ["opencode", "export", "ses_123"])

    def test_opencode_verifier_launches_resolved_windows_cmd_for_run_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            resolved = r"C:\Users\sergi\AppData\Roaming\npm\opencode.CMD"

            with (
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.shutil.which",
                    return_value=resolved,
                ),
                patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock,
            ):
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=[resolved, "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_cmd"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=[resolved, "export", "ses_cmd"],
                        returncode=0,
                        stdout=json.dumps({"events": []}),
                        stderr="",
                    ),
                ]

                run_verifier(
                    scenario="datasource_documentation",
                    run_id="resolved-windows-cmd",
                    output_root=output_root,
                    repo_root=Path.cwd(),
                )

            self.assertEqual(run_mock.call_args_list[0].args[0][:2], [resolved, "run"])
            self.assertEqual(run_mock.call_args_list[1].args[0], [resolved, "export", "ses_cmd"])

    def test_opencode_verifier_decodes_subprocess_output_with_utf8_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(kwargs["encoding"], "utf-8")
                self.assertEqual(kwargs["errors"], "replace")
                if command[:2] == ["opencode", "run"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=b'{"sessionID": "ses_utf8"}',
                        stderr=b"warning: invalid byte: \xff",
                    )
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"events": []}), stderr="")

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run", side_effect=fake_run):
                result = run_verifier(
                    scenario="datasource_documentation",
                    run_id="utf8-replacement-output",
                    output_root=output_root,
                    repo_root=Path.cwd(),
                )

            self.assertTrue(result.manifest_path.is_file())
            stderr_path = result.manifest_path.parent / "diagnostics" / "opencode-run.stderr.txt"
            self.assertIn("�", stderr_path.read_text(encoding="utf-8"))

    def test_opencode_verifier_treats_missing_stdout_stderr_as_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=0, stdout=None, stderr=None
                )

                with self.assertRaisesRegex(OpenCodeVerifierError, "missing-sessionID"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="missing-stdout-stderr",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

            run_root = output_root / "missing-stdout-stderr"
            self.assertEqual((run_root / "diagnostics" / "opencode-run.stdout.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual((run_root / "diagnostics" / "opencode-run.stderr.txt").read_text(encoding="utf-8"), "")

    def test_opencode_verifier_wraps_run_launch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                side_effect=FileNotFoundError("opencode"),
            ):
                with self.assertRaisesRegex(OpenCodeVerifierError, "opencode-run-launch-failed"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="missing-binary-run",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

    def test_opencode_verifier_main_reports_launch_failure_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = StringIO()

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                side_effect=OSError("opencode unavailable"),
            ):
                with redirect_stderr(stderr):
                    exit_code = opencode_verifier_main(
                        [
                            "--scenario",
                            "datasource_documentation",
                            "--run-id",
                            "missing-binary-cli",
                            "--output-root",
                            str(Path(tmp) / "runs"),
                            "--repo-root",
                            str(Path.cwd()),
                        ]
                    )

            error_text = stderr.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("error: opencode-run-launch-failed: opencode unavailable", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_opencode_verifier_main_reports_missing_prompt_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subject = Path(tmp) / "subject"
            subject.mkdir()

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.prepare_subject",
                return_value=SimpleNamespace(subject_path=subject),
            ):
                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="missing-prompt-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: missing-prompt:", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_opencode_verifier_main_reports_empty_prompt_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subject = Path(tmp) / "subject"
            subject.mkdir()
            (subject / "PROMPT.md").write_text("\n\t\n", encoding="utf-8")

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.prepare_subject",
                return_value=SimpleNamespace(subject_path=subject),
            ):
                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="empty-prompt-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: missing-prompt: empty prompt", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_opencode_verifier_main_reports_missing_session_id_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=0, stdout=json.dumps({"message": "ok"}), stderr=""
                )

                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="missing-session-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: missing-sessionID:", error_text)
            self.assertNotIn("Traceback", error_text)
            self.assertEqual(run_mock.call_count, 1)

    def test_opencode_verifier_main_reports_run_nonzero_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=7, stdout="", stderr="run failed"
                )

                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="run-nonzero-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: opencode-run-failed: exit 7", error_text)
            self.assertNotIn("Traceback", error_text)
            self.assertEqual(run_mock.call_count, 1)

    def test_opencode_verifier_main_reports_export_nonzero_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"], returncode=0, stdout=json.dumps({"sessionID": "ses_cli"}), stderr=""
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_cli"], returncode=1, stdout="", stderr="no export"
                    ),
                ]

                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="export-nonzero-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: export-failed: exit 1", error_text)
            self.assertNotIn("Traceback", error_text)
            self.assertEqual(run_mock.call_count, 2)

    def test_opencode_verifier_main_reports_export_launch_failure_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"], returncode=0, stdout=json.dumps({"sessionID": "ses_cli"}), stderr=""
                    ),
                    OSError("export unavailable"),
                ]

                exit_code, error_text = self._run_opencode_verifier_main_for_error(
                    tmp, run_id="export-launch-cli"
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: opencode-export-launch-failed: export unavailable", error_text)
            self.assertNotIn("Traceback", error_text)
            self.assertEqual(run_mock.call_count, 2)

    def test_opencode_verifier_main_reports_invalid_export_json_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = StringIO()

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"], returncode=0, stdout=json.dumps({"sessionID": "ses_bad_json"}), stderr=""
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_bad_json"], returncode=0, stdout="{not-json", stderr=""
                    ),
                ]
                with redirect_stderr(stderr):
                    exit_code = opencode_verifier_main(
                        [
                            "--scenario",
                            "datasource_documentation",
                            "--run-id",
                            "invalid-export-json-cli",
                            "--output-root",
                            str(Path(tmp) / "runs"),
                            "--repo-root",
                            str(Path.cwd()),
                        ]
                    )

            error_text = stderr.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("error: export-invalid-json: opencode export did not emit JSON", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_opencode_verifier_module_reports_prepare_failure_without_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.eval.blind_agentic.run_opencode_verifier",
                    "--scenario",
                    "missing_scenario",
                    "--run-id",
                    "module-prepare-failure",
                    "--output-root",
                    str(Path(tmp) / "runs"),
                    "--repo-root",
                    str(Path.cwd()),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("error: Unknown blind subject scenario: missing_scenario", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_opencode_verifier_wraps_export_launch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"], returncode=0, stdout=json.dumps({"sessionID": "ses_123"}), stderr=""
                    ),
                    OSError("export unavailable"),
                ]

                with self.assertRaisesRegex(OpenCodeVerifierError, "opencode-export-launch-failed"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="missing-binary-export",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

    def test_opencode_verifier_rejects_missing_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subject = Path(tmp) / "subject"
            subject.mkdir()

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.prepare_subject",
                return_value=SimpleNamespace(subject_path=subject),
            ):
                with self.assertRaisesRegex(OpenCodeVerifierError, "missing-prompt"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="missing-prompt",
                        output_root=Path(tmp) / "runs",
                        repo_root=Path.cwd(),
                    )

    def test_opencode_verifier_rejects_empty_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subject = Path(tmp) / "subject"
            subject.mkdir()
            (subject / "PROMPT.md").write_text("\n\t\n", encoding="utf-8")

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.prepare_subject",
                return_value=SimpleNamespace(subject_path=subject),
            ):
                with self.assertRaisesRegex(OpenCodeVerifierError, "empty prompt"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="empty-prompt",
                        output_root=Path(tmp) / "runs",
                        repo_root=Path.cwd(),
                    )

    def test_opencode_verifier_registers_workspace_and_exports_session_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            calls: list[str] = []

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append("run" if command[:2] == ["opencode", "run"] else "export")
                if command[:2] == ["opencode", "run"]:
                    self.assertIn("Use BrainDS MCP action brain_ds_open_workspace", kwargs["input"])
                    self.assertEqual(command[2:6], ["--agent", "brain-ds-orchestrator", "--format", "json"])
                    self.assertIn("BRAIN_DS_HOME", kwargs["env"])
                    return subprocess.CompletedProcess(command, 0, json.dumps({"sessionID": "ses_order"}), "run diagnostics")
                return subprocess.CompletedProcess(command, 0, json.dumps({"events": []}), "export diagnostics")

            def fake_register(path: Path, *, name: str | None = None) -> dict[str, str]:
                del name
                calls.append("register")
                return {"path": str(path), "name": "subject"}

            with (
                patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run", side_effect=fake_run),
                patch("tests.eval.blind_agentic.run_opencode_verifier.workspaces.register_workspace", side_effect=fake_register),
            ):
                result = run_verifier(
                    scenario="datasource_documentation",
                    run_id="ordered-run",
                    output_root=output_root,
                    repo_root=Path.cwd(),
                )

            self.assertEqual(calls, ["register", "run", "export"])
            self.assertEqual(result.session_id, "ses_order")
            self.assertTrue(result.export_path.is_file())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["session_id"], "ses_order")
            self.assertEqual(manifest["session_id_source_alias"], "sessionID")
            self.assertEqual(manifest["brain_ds_home"], (output_root / "ordered-run" / "brain_ds_home").as_posix())
            self.assertEqual(manifest["prompt_path"], (result.subject_path / "PROMPT.md").as_posix())
            self.assertEqual(
                manifest["workspace_registration"],
                {
                    "status": "registered",
                    "path": result.subject_path.as_posix(),
                    "registry_path": (output_root / "ordered-run" / "brain_ds_home" / "workspaces.json").as_posix(),
                },
            )
            self.assertEqual(manifest["opencode_run"]["command"][3], "brain-ds-orchestrator")
            self.assertEqual(manifest["opencode_run"]["stdout_path"], "diagnostics/opencode-run.stdout.jsonl")
            self.assertEqual(manifest["opencode_run"]["stderr_path"], "diagnostics/opencode-run.stderr.txt")
            self.assertTrue((result.manifest_path.parent / manifest["opencode_run"]["stdout_path"]).is_file())
            self.assertTrue((result.manifest_path.parent / manifest["opencode_run"]["stderr_path"]).is_file())
            self.assertEqual(manifest["opencode_export"]["command"], ["opencode", "export", "ses_order"])
            self.assertEqual(manifest["opencode_export"]["stderr_path"], "diagnostics/opencode-export.stderr.txt")
            self.assertTrue((result.manifest_path.parent / manifest["opencode_export"]["stderr_path"]).is_file())

    def test_opencode_verifier_same_run_failure_clears_stale_success_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            run_id = "rerun-clears-stale-success"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_success"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_success"],
                        returncode=0,
                        stdout=json.dumps({"events": [{"sessionID": "ses_success"}]}),
                        stderr="",
                    ),
                ]

                first = run_verifier(
                    scenario="datasource_documentation",
                    run_id=run_id,
                    output_root=output_root,
                    repo_root=Path.cwd(),
                )

            run_root = output_root / run_id
            manifest_path = run_root / "opencode-verifier-manifest.json"
            export_path = run_root / "opencode-export" / "session.json"
            registry_path = run_root / "brain_ds_home" / "workspaces.json"

            self.assertEqual(first.manifest_path, manifest_path)
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(export_path.is_file())
            self.assertTrue(registry_path.is_file())

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=7, stdout="", stderr="run failed"
                )

                with self.assertRaisesRegex(OpenCodeVerifierError, "opencode-run-failed: exit 7"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id=run_id,
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

            self.assertFalse(manifest_path.exists())
            self.assertFalse(export_path.exists())
            self.assertTrue((run_root / "diagnostics" / "opencode-run.stderr.txt").is_file())
            self.assertTrue(registry_path.is_file())
            self.assertNotIn("ses_success", registry_path.read_text(encoding="utf-8"))

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

    def _run_opencode_verifier_main_for_error(self, tmp: str, *, run_id: str) -> tuple[int, str]:
        stderr = StringIO()
        with redirect_stderr(stderr):
            exit_code = opencode_verifier_main(
                [
                    "--scenario",
                    "datasource_documentation",
                    "--run-id",
                    run_id,
                    "--output-root",
                    str(Path(tmp) / "runs"),
                    "--repo-root",
                    str(Path.cwd()),
                ]
            )
        return exit_code, stderr.getvalue()
