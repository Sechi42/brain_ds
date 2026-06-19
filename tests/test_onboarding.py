import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui import cli
from brain_ds.ui.onboarding import Style, banner, branded_print, mascot, run_onboard


class BrandingTests(unittest.TestCase):
    def test_mascot_is_ascii_hippo_with_network_labels(self):
        art = mascot()

        self.assertTrue(art.strip())
        art.encode("ascii")
        self.assertIn("HIPPO", art)
        self.assertIn("ROLES", art)
        self.assertIn("DATA SOURCES", art)
        self.assertIn("o--", art)
        self.assertIn("/____", art)

    def test_mascot_preserves_decision_and_relationship_logo_tokens(self):
        art = mascot()

        art.encode("ascii")
        self.assertIn("DECISIONS", art)
        self.assertIn("BUSINESS RELATIONSHIPS", art)
        self.assertIn("DEPARTMENTS", art)
        self.assertIn("(oo)", art)

    def test_banner_contains_product_name_and_command_context(self):
        text = banner("setup")

        text.encode("ascii")
        self.assertIn("BrainDS", text)
        self.assertIn("setup", text)
        self.assertIn("Enterprise Data & Knowledge Mapper", text)

    def test_branded_print_quiet_suppresses_human_output(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            branded_print("Config target written: .mcp.json", style=Style.SUCCESS, quiet=True)

        self.assertEqual(stdout.getvalue(), "")

    def test_branded_print_keeps_machine_readable_message_intact(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            branded_print("Config target written: .mcp.json", style=Style.SUCCESS)

        self.assertIn("Config target written: .mcp.json", stdout.getvalue())


class OnboardCommandTests(unittest.TestCase):
    def test_onboard_help_lists_orchestration_flags(self):
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as ctx, redirect_stdout(stdout):
            cli.main(["onboard", "--help"])

        self.assertEqual(ctx.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("--project-root", help_text)
        self.assertIn("--agent", help_text)
        self.assertIn("--global", help_text)
        self.assertIn("--project", help_text)
        self.assertIn("--agent-deploy", help_text)
        self.assertIn("--dry-run", help_text)
        self.assertIn("--json", help_text)
        self.assertIn("--quiet", help_text)

    def test_run_onboard_json_wraps_setup_and_opencode_installer_for_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup_result = {
                "project_root": str(root.resolve()),
                "agents": ["claude", "opencode"],
                "written": [".mcp.json", ".opencode/opencode.json"],
                "checklist": ["restart your agent client"],
            }
            installer_result = {
                "mode": "project",
                "agent_deploy": True,
                "returncode": 0,
            }
            args = Namespace(
                project_root=str(root),
                agent="both",
                install_scope="project",
                agent_deploy=True,
                dry_run=False,
                json=True,
                quiet=True,
                force=True,
            )
            stdout = io.StringIO()

            with patch("brain_ds.ui.onboarding.apply_setup", return_value=setup_result) as setup:
                with patch("brain_ds.ui.onboarding._run_opencode_installer", return_value=installer_result) as installer:
                    with redirect_stdout(stdout):
                        code = run_onboard(args)

            self.assertEqual(code, 0)
            setup.assert_called_once_with(root.resolve(), agent="both")
            installer.assert_called_once_with(root.resolve(), scope="project", agent_deploy=True, dry_run=False)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["project_root"], str(root.resolve()))
            self.assertEqual(payload["agents"], ["claude", "opencode"])
            self.assertEqual(payload["written"], [".mcp.json", ".opencode/opencode.json"])
            self.assertEqual(payload["checklist"], ["restart your agent client"])
            self.assertEqual(payload["opencode_install"], installer_result)

    def test_run_onboard_missing_installer_returns_engine_error_with_stderr_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing-install-opencode.sh"
            setup_result = {
                "project_root": str(root.resolve()),
                "agents": ["opencode"],
                "written": [".opencode/opencode.json"],
                "checklist": [],
            }
            args = Namespace(
                project_root=str(root),
                agent="opencode",
                install_scope="project",
                agent_deploy=False,
                dry_run=False,
                json=False,
                quiet=True,
                force=True,
            )
            stderr = io.StringIO()

            with patch("brain_ds.ui.onboarding.apply_setup", return_value=setup_result):
                with patch("brain_ds.ui.onboarding._installer_script_path", return_value=missing):
                    with patch("sys.stderr", stderr):
                        code = run_onboard(args)

            self.assertGreaterEqual(code, 3)
            self.assertIn("OpenCode installer not found", stderr.getvalue())
            self.assertIn(str(missing), stderr.getvalue())

    def test_cli_dispatches_onboard_to_orchestrator(self):
        with patch("brain_ds.ui.cli.run_onboard", return_value=0) as run:
            code = cli.main(["onboard", "--project-root", ".", "--agent", "claude", "--quiet"])

        self.assertEqual(code, 0)
        args = run.call_args.args[0]
        self.assertEqual(args.command, "onboard")
        self.assertEqual(args.agent, "claude")
        self.assertTrue(args.quiet)

    def test_run_onboard_claude_only_skips_opencode_installer_and_shows_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup_result = {
                "project_root": str(root.resolve()),
                "agents": ["claude"],
                "written": [".mcp.json"],
                "checklist": ["restart your agent client"],
            }
            args = Namespace(
                project_root=str(root),
                agent="claude",
                install_scope="project",
                agent_deploy=False,
                dry_run=False,
                json=False,
                quiet=False,
                force=True,
            )
            stdout = io.StringIO()

            with patch("brain_ds.ui.onboarding.apply_setup", return_value=setup_result):
                with patch("brain_ds.ui.onboarding._run_opencode_installer") as installer:
                    with redirect_stdout(stdout):
                        code = run_onboard(args)

            self.assertEqual(code, 0)
            installer.assert_not_called()
            output = stdout.getvalue()
            self.assertIn("BrainDS :: onboard", output)
            self.assertIn("HIPPO", output)
            self.assertIn("Config target written: .mcp.json", output)

    def test_run_onboard_dry_run_preserves_setup_no_write_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = Namespace(
                project_root=str(root),
                agent="both",
                install_scope="project",
                agent_deploy=False,
                dry_run=True,
                json=True,
                quiet=True,
                force=True,
            )
            stdout = io.StringIO()

            with patch("brain_ds.ui.onboarding.apply_setup", side_effect=AssertionError("must not write")):
                with patch(
                    "brain_ds.ui.onboarding._run_opencode_installer",
                    return_value={"mode": "project", "agent_deploy": False, "returncode": 0, "skipped": True},
                ):
                    with redirect_stdout(stdout):
                        code = run_onboard(args)

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["agents"], ["claude", "opencode"])
            self.assertEqual(payload["written"], [])
            self.assertFalse((root / ".brain_ds" / "store.db").exists())
            self.assertFalse((root / ".mcp.json").exists())


if __name__ == "__main__":
    unittest.main()
