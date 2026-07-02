from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from typing import Any, TypedDict, cast

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


REPO_ROOT = Path(__file__).resolve().parent.parent


class _PendingQuestion(TypedDict):
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str


class BlindAgenticFixtureLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="blind-agentic-loop-")
        self._opencode_which = patch(
            "tests.eval.blind_agentic.run_opencode_verifier.shutil.which",
            return_value=None,
        )
        self._opencode_which.start()
        self._previous_pythonpath = os.environ.get("PYTHONPATH")
        self._previous_output_root = os.environ.get("BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT")
        pythonpath = REPO_ROOT.as_posix()
        if self._previous_pythonpath is not None:
            pythonpath = f"{pythonpath}{os.pathsep}{self._previous_pythonpath}"
        self._sdd_env = patch.dict(os.environ, {"BRAIN_DS_SDD_CHANGE": "agentic-evaluation-lab"})
        self._sdd_env.start()
        os.environ["BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT"] = self._tmp.name
        os.environ["PYTHONPATH"] = pythonpath

    def tearDown(self) -> None:
        self._sdd_env.stop()
        if self._previous_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = self._previous_pythonpath
        if self._previous_output_root is None:
            os.environ.pop("BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT", None)
        else:
            os.environ["BRAIN_DS_BLIND_AGENTIC_OUTPUT_ROOT"] = self._previous_output_root
        self._opencode_which.stop()
        self._tmp.cleanup()

    def test_opencode_verifier_builds_required_orchestrator_command(self) -> None:
        command = build_opencode_run_command(Path("/tmp/subject"), model="opencode/test-model")

        self.assertEqual(
            command[:6], ["opencode", "run", "--agent", "brain-ds-orchestrator", "--format", "json"]
        )
        self.assertEqual(command[-4:], ["--dir", "/tmp/subject", "--model", "opencode/test-model"])

    def test_opencode_verifier_rejects_wrong_orchestrator(self) -> None:
        with self.assertRaisesRegex(OpenCodeVerifierError, "wrong-agent"):
            build_opencode_run_command(Path("/tmp/subject"), agent="general")

    def test_opencode_verifier_fails_fast_without_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"],
                    returncode=0,
                    stdout=json.dumps({"message": "ok"}),
                    stderr="",
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
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_123"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_123"],
                        returncode=1,
                        stdout="",
                        stderr="no export",
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
                self.assertEqual(
                    run_mock.call_args_list[1].args[0], ["opencode", "export", "ses_123"]
                )

    def test_opencode_verifier_cleans_default_workspace_after_run_failure_outside_pytest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            non_pytest_env = dict(os.environ)
            non_pytest_env.pop("PYTEST_CURRENT_TEST", None)

            with (
                patch.dict(os.environ, non_pytest_env, clear=True),
                patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock,
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.workspaces.unregister_workspace",
                    return_value=True,
                ) as unregister_mock,
            ):
                run_mock.return_value = subprocess.CompletedProcess(
                    args=["opencode", "run"], returncode=7, stdout="", stderr="run failed"
                )

                with self.assertRaisesRegex(OpenCodeVerifierError, "opencode-run-failed: exit 7"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="run-failure-cleans-default",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

            self.assertEqual(unregister_mock.call_count, 1)
            self.assertEqual(
                unregister_mock.call_args.args[0],
                output_root / "run-failure-cleans-default" / "subject",
            )

    def test_opencode_verifier_cleans_default_workspace_after_export_failure_outside_pytest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            non_pytest_env = dict(os.environ)
            non_pytest_env.pop("PYTEST_CURRENT_TEST", None)

            with (
                patch.dict(os.environ, non_pytest_env, clear=True),
                patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock,
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.workspaces.unregister_workspace",
                    return_value=True,
                ) as unregister_mock,
            ):
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_cleanup"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_cleanup"],
                        returncode=1,
                        stdout="",
                        stderr="no export",
                    ),
                ]

                with self.assertRaisesRegex(OpenCodeVerifierError, "export-failed"):
                    run_verifier(
                        scenario="datasource_documentation",
                        run_id="export-failure-cleans-default",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

            self.assertEqual(unregister_mock.call_count, 1)
            self.assertEqual(
                unregister_mock.call_args.args[0],
                output_root / "export-failure-cleans-default" / "subject",
            )

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

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[Any]:
                self.assertEqual(kwargs["encoding"], "utf-8")
                self.assertEqual(kwargs["errors"], "replace")
                if command[:2] == ["opencode", "run"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=b'{"sessionID": "ses_utf8"}',
                        stderr=b"warning: invalid byte: \xff",
                    )
                return subprocess.CompletedProcess(
                    command, 0, stdout=json.dumps({"events": []}), stderr=""
                )

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                side_effect=fake_run,
            ):
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
            self.assertEqual(
                (run_root / "diagnostics" / "opencode-run.stdout.jsonl").read_text(
                    encoding="utf-8"
                ),
                "",
            )
            self.assertEqual(
                (run_root / "diagnostics" / "opencode-run.stderr.txt").read_text(encoding="utf-8"),
                "",
            )

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

    def test_opencode_verifier_main_requires_sdd_change_before_running_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = StringIO()

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock,
                redirect_stderr(stderr),
            ):
                exit_code = opencode_verifier_main(
                    [
                        "--scenario",
                        "datasource_documentation",
                        "--run-id",
                        "missing-sdd-cli",
                        "--output-root",
                        str(Path(tmp) / "runs"),
                        "--repo-root",
                        str(Path.cwd()),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error: sdd_change", stderr.getvalue())
            self.assertEqual(run_mock.call_count, 0)

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
                    args=["opencode", "run"],
                    returncode=0,
                    stdout=json.dumps({"message": "ok"}),
                    stderr="",
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
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_cli"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_cli"],
                        returncode=1,
                        stdout="",
                        stderr="no export",
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
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_cli"}),
                        stderr="",
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
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_bad_json"}),
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["opencode", "export", "ses_bad_json"],
                        returncode=0,
                        stdout="{not-json",
                        stderr="",
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
            self.assertIn(
                "error: export-invalid-json: opencode export did not emit JSON", error_text
            )
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
        self.assertIn("error: sdd_change: Unknown scenario", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_opencode_verifier_wraps_export_launch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            with patch("tests.eval.blind_agentic.run_opencode_verifier.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["opencode", "run"],
                        returncode=0,
                        stdout=json.dumps({"sessionID": "ses_123"}),
                        stderr="",
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
                    prompt = cast(str, kwargs["input"])
                    self.assertIn("Use BrainDS MCP action brain_ds_open_workspace", prompt)
                    self.assertIn(
                        "path "
                        + output_root.joinpath("ordered-run", "subject")
                        .resolve(strict=False)
                        .as_posix(),
                        prompt,
                    )
                    self.assertEqual(
                        command[2:6], ["--agent", "brain-ds-orchestrator", "--format", "json"]
                    )
                    self.assertIn("BRAIN_DS_HOME", cast(dict[str, str], kwargs["env"]))
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps({"sessionID": "ses_order"}), "run diagnostics"
                    )
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"events": []}), "export diagnostics"
                )

            def fake_register(path: Path, *, name: str | None = None) -> dict[str, str]:
                del name
                calls.append("register")
                return {"path": str(path), "name": "subject"}

            with (
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                    side_effect=fake_run,
                ),
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.workspaces.register_workspace",
                    side_effect=fake_register,
                ),
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
            self.assertEqual(
                manifest["brain_ds_home"],
                (output_root / "ordered-run" / "brain_ds_home").as_posix(),
            )
            self.assertEqual(
                manifest["prompt_path"], (result.subject_path / "PROMPT.md").as_posix()
            )
            self.assertEqual(manifest["workspace_registration"]["status"], "registered")
            self.assertEqual(
                manifest["workspace_registration"]["path"], result.subject_path.as_posix()
            )
            self.assertEqual(
                manifest["workspace_registration"]["registry_path"],
                (output_root / "ordered-run" / "brain_ds_home" / "workspaces.json").as_posix(),
            )
            self.assertEqual(
                manifest["workspace_registration"]["default_registry"]["status"], "skipped"
            )
            self.assertEqual(manifest["opencode_run"]["command"][3], "brain-ds-orchestrator")
            self.assertEqual(
                manifest["opencode_run"]["stdout_path"], "diagnostics/opencode-run.stdout.jsonl"
            )
            self.assertEqual(
                manifest["opencode_run"]["stderr_path"], "diagnostics/opencode-run.stderr.txt"
            )
            self.assertTrue(
                (result.manifest_path.parent / manifest["opencode_run"]["stdout_path"]).is_file()
            )
            self.assertTrue(
                (result.manifest_path.parent / manifest["opencode_run"]["stderr_path"]).is_file()
            )
            self.assertEqual(
                manifest["opencode_export"]["command"], ["opencode", "export", "ses_order"]
            )
            self.assertEqual(
                manifest["opencode_export"]["stderr_path"], "diagnostics/opencode-export.stderr.txt"
            )
            self.assertTrue(
                (result.manifest_path.parent / manifest["opencode_export"]["stderr_path"]).is_file()
            )
            self.assertEqual(manifest["lineage"]["sdd_change"], "agentic-evaluation-lab")
            self.assertRegex(manifest["lineage"]["commit_sha"], r"^[0-9a-f]{40}$")
            self.assertEqual(manifest["selected_path"]["path_id"], "doc-map")
            self.assertEqual(
                manifest["path_plan_version"], manifest["selected_path"]["path_plan_version"]
            )
            self.assertIn(manifest["comparability"]["status"], {"comparable", "non_comparable"})

    def test_opencode_verifier_selects_graph_qa_for_revops_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["opencode", "run"]:
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps({"sessionID": "ses_graph_qa"}), "run diagnostics"
                    )
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"events": []}), "export diagnostics"
                )

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                side_effect=fake_run,
            ):
                result = run_verifier(
                    scenario="revops_growth",
                    run_id="graph-qa-run",
                    output_root=output_root,
                    repo_root=Path.cwd(),
                )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["selected_path"]["path_id"], "graph-qa")
            self.assertEqual(manifest["selected_path"]["scenario"], "revops_growth")
            self.assertEqual(manifest["scenario"], "revops_growth")
            if manifest["comparability"]["key"] is not None:
                self.assertEqual(manifest["comparability"]["key"]["path_id"], "graph-qa")
                self.assertEqual(manifest["comparability"]["key"]["scenario"], "revops_growth")

    def test_opencode_verifier_selects_each_slice2_path_without_leaking_other_path_context(
        self,
    ) -> None:
        cases = {
            "kpi-lineage": "kpi_lineage",
            "currency-elicitation": "currency_elicitation",
        }

        for path_id, scenario in cases.items():
            with self.subTest(path_id=path_id), tempfile.TemporaryDirectory() as tmp:
                output_root = Path(tmp) / "runs"

                def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                    if command[:2] == ["opencode", "run"]:
                        prompt = cast(str, kwargs["input"])
                        self.assertIn("Use BrainDS MCP action brain_ds_open_workspace", prompt)
                        self.assertNotIn("doc-map", prompt)
                        self.assertNotIn("graph-qa", prompt)
                        return subprocess.CompletedProcess(
                            command, 0, json.dumps({"sessionID": f"ses_{scenario}"}), ""
                        )
                    return subprocess.CompletedProcess(command, 0, json.dumps({"events": []}), "")

                with patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                    side_effect=fake_run,
                ):
                    result = run_verifier(
                        path_id=path_id,
                        run_id=f"{scenario}-run",
                        output_root=output_root,
                        repo_root=Path.cwd(),
                    )

                manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(result.path_id, path_id)
                self.assertEqual(result.scenario, scenario)
                self.assertEqual(manifest["selected_path"]["path_id"], path_id)
                self.assertEqual(manifest["selected_path"]["scenario"], scenario)
                self.assertEqual(manifest["scenario"], scenario)
                self.assertEqual(
                    manifest["comparability"]["key"]["path_id"]
                    if manifest["comparability"]["key"] is not None
                    else path_id,
                    path_id,
                )

    def test_prepare_collect_score_loop_supports_slice2_path_metadata(self) -> None:
        cases = {
            "kpi_lineage": ("kpi-lineage", "kpi-lineage-v1", "kpi-lineage-fixture-v1"),
            "currency_elicitation": (
                "currency-elicitation",
                "currency-elicitation-v1",
                "currency-elicitation-fixture-v1",
            ),
        }

        for scenario, (path_id, prompt_version, fixture_version) in cases.items():
            with self.subTest(scenario=scenario):
                run_id = f"{scenario}-loop-001"
                workspace = prepare_subject(
                    scenario=scenario,
                    run_id=run_id,
                    output_root=Path("tmp") / "blind-agentic-loop-test",
                )
                self._write_slice2_subject_outputs(workspace.subject_path, scenario=scenario)

                bundle = collect_evidence(
                    scenario=scenario,
                    run_id=run_id,
                    subject_path=workspace.subject_path,
                    evidence_path=workspace.subject_path.parent / "evidence",
                    repo_root=Path.cwd(),
                )
                report = score_evidence(
                    scenario=scenario,
                    evidence_path=bundle.evidence_path,
                    out_path=workspace.subject_path.parent / "report.json",
                    repo_root=Path.cwd(),
                )
                manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

                self.assertEqual(manifest["selected_path"]["path_id"], path_id)
                self.assertEqual(manifest["run_metadata"]["prompt_version"], prompt_version)
                self.assertEqual(manifest["run_metadata"]["fixture_version"], fixture_version)
                self.assertEqual(report["selected_path"]["path_id"], path_id)
                self.assertEqual(report["overall_score_0_5"], 5.0)

    def test_opencode_verifier_uses_subject_cwd_with_run_local_mcp_config_and_seeds_subject_graph(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "runs"
            repo_root = Path.cwd()

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["opencode", "run"]:
                    dir_index = command.index("--dir") + 1
                    self.assertTrue(Path(command[dir_index]).is_absolute())
                    self.assertEqual(Path(command[dir_index]).name, "subject")
                    subject = Path(cast(Path, kwargs["cwd"]))
                    self.assertEqual(subject.name, "subject")
                    env = cast(dict[str, str], kwargs["env"])
                    self.assertEqual(env["BRAIN_DS_PROJECT_ROOT"], subject.as_posix())
                    self.assertEqual(
                        env["BRAIN_DS_HOME"],
                        (output_root / "absolute-dir-seeded-graph" / "brain_ds_home")
                        .resolve(strict=False)
                        .as_posix(),
                    )
                    config = json.loads(
                        (subject / ".opencode" / "opencode.json").read_text(encoding="utf-8")
                    )
                    server = config["mcp"]["brain_ds"]
                    self.assertEqual(server["command"][-2:], ["--project-root", subject.as_posix()])
                    self.assertEqual(
                        server["environment"]["BRAIN_DS_PROJECT_ROOT"], subject.as_posix()
                    )
                    self.assertEqual(server["environment"]["BRAIN_DS_HOME"], env["BRAIN_DS_HOME"])
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps({"sessionID": "ses_abs"}), ""
                    )
                self.assertEqual(Path(cast(Path, kwargs["cwd"])).name, "subject")
                return subprocess.CompletedProcess(command, 0, json.dumps({"events": []}), "")

            with patch(
                "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                side_effect=fake_run,
            ):
                result = run_verifier(
                    scenario="datasource_documentation",
                    run_id="absolute-dir-seeded-graph",
                    output_root=output_root,
                    repo_root=repo_root,
                )

            graph_db = result.subject_path / ".brain_ds" / "store.db"
            self.assertTrue(graph_db.is_file())
            with GraphStore(str(graph_db), read_only=True) as store:
                self.assertEqual(
                    [graph.id for graph in store.list_graphs()], ["helios-datasource-docs"]
                )
                self.assertEqual(
                    sorted(node.id for node in store.query_nodes("helios-datasource-docs")),
                    ["source-customers", "source-orders"],
                )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["opencode_run"]["cwd"], result.subject_path.as_posix())
            self.assertEqual(manifest["opencode_mcp_config"]["status"], "written")
            self.assertEqual(
                manifest["opencode_mcp_config"]["brain_ds_home"],
                (output_root / "absolute-dir-seeded-graph" / "brain_ds_home")
                .resolve(strict=False)
                .as_posix(),
            )
            self.assertEqual(manifest["subject_graph_seed"]["status"], "seeded")
            self.assertEqual(manifest["subject_graph_seed"]["graph_id"], "helios-datasource-docs")

    def test_opencode_verifier_temporarily_overrides_repo_opencode_mcp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            subject = root / "subject"
            config_path = root / ".opencode" / "opencode.json"
            subject.mkdir(parents=True)
            (subject / "PROMPT.md").write_text("Document this datasource.", encoding="utf-8")
            (root / "README.md").write_text("repo fixture\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
            )
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "test fixture"], cwd=root, check=True, capture_output=True
            )
            config_path.parent.mkdir(parents=True)
            original_config = {
                "mcp": {
                    "brain_ds": {
                        "type": "local",
                        "enabled": True,
                        "command": ["brain_ds", "mcp", "--project-root", "C:/repo"],
                        "environment": {"BRAIN_DS_PROJECT_ROOT": "C:/repo"},
                    },
                    "engram": {"type": "local", "command": ["engram", "mcp"]},
                }
            }
            config_path.write_text(json.dumps(original_config), encoding="utf-8")

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["opencode", "run"]:
                    live_config = json.loads(config_path.read_text(encoding="utf-8"))
                    server = live_config["mcp"]["brain_ds"]
                    self.assertEqual(server["command"][-2:], ["--project-root", subject.as_posix()])
                    self.assertEqual(
                        server["environment"]["BRAIN_DS_PROJECT_ROOT"], subject.as_posix()
                    )
                    self.assertEqual(
                        server["environment"]["BRAIN_DS_HOME"],
                        cast(dict[str, str], kwargs["env"])["BRAIN_DS_HOME"],
                    )
                    self.assertEqual(live_config["mcp"]["engram"], original_config["mcp"]["engram"])
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps({"sessionID": "ses_cfg"}), ""
                    )
                return subprocess.CompletedProcess(command, 0, json.dumps({"events": []}), "")

            with (
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.prepare_subject",
                    return_value=SimpleNamespace(subject_path=subject),
                ),
                patch(
                    "tests.eval.blind_agentic.run_opencode_verifier.subprocess.run",
                    side_effect=fake_run,
                ),
            ):
                run_verifier(
                    scenario="datasource_documentation",
                    run_id="repo-config-override",
                    output_root=Path(tmp) / "runs",
                    repo_root=root,
                )

            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8")), original_config)

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
            "selected_path": {"path_id": "doc-map", "path_plan_version": "2026-06-30.pr1"},
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
                    "rubric_version": "datasource-documentation-rubric-v1",
                    "trace_schema_version": "2026-06-27.pr1",
                    "report_schema_version": "2026-06-27.pr4",
                },
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

    def _write_slice2_subject_outputs(self, subject_path: Path, *, scenario: str) -> None:
        brain_ds = subject_path / ".brain_ds"
        brain_ds.mkdir(parents=True, exist_ok=True)
        graph_id = "kpi_lineage_graph" if scenario == "kpi_lineage" else "currency_elicitation_graph"
        with GraphStore(str(brain_ds / "store.db")) as store:
            store.create_graph(graph_id, name=scenario.replace("_", " ").title())
            if scenario == "kpi_lineage":
                nodes = [
                    {"id": "kpi-gross-margin", "label": "Gross Margin", "type": "KPI"},
                    {"id": "source-finance", "label": "Finance Ledger", "type": "Data Source"},
                    {"id": "source-billing", "label": "Billing Events", "type": "Data Source"},
                ]
                edges = [
                    {"source": "source-finance", "target": "kpi-gross-margin", "label": "measures", "weight": 1.0},
                    {"source": "source-billing", "target": "kpi-gross-margin", "label": "depends_on", "weight": 1.0},
                ]
                generated_text = (
                    "Gross Margin lineage uses Finance Ledger and Billing Events. "
                    "Business next actions include source ownership review, KPI definitions, "
                    "explicit assumptions, and data gaps for metric owners."
                )
            else:
                nodes = [
                    {"id": "source-customer-success", "label": "Customer Success Notes", "type": "Data Source"},
                    {"id": "question-currency", "label": "Confirm data currency owner", "type": "Question"},
                ]
                edges = [
                    {"source": "source-customer-success", "target": "question-currency", "label": "raises", "weight": 1.0},
                ]
                generated_text = (
                    "Customer Success Notes need currency confirmation. Business next actions "
                    "include source ownership review, KPI definitions impacted by freshness, "
                    "explicit assumptions, and data gaps for stakeholder follow-up."
                )
            for node in nodes:
                store.node_repo.upsert_node(graph_id, {**node, "details": {}})
            for edge in edges:
                store.edge_repo.upsert_edge(graph_id, edge)
            store.insert_pending_question(
                graph_id,
                target_node_id=nodes[0]["id"],
                gap_kind="currency",
                entity_type="Data Source",
                question_text="Who confirms the current data currency and owner?",
                stakeholder_owner="Data Steward",
            )
        (brain_ds / "setup.json").write_text(json.dumps({"agents": ["opencode"]}), encoding="utf-8")
        generated = subject_path / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "diagnosis.md").write_text(generated_text, encoding="utf-8")

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
