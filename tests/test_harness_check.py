"""Tests for local harness parity helpers."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from brain_ds.harness_check import (
    check_project_mcp_entries,
    check_skills_mirror,
    harness_check_main,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class HarnessCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="brain-ds-harness-check-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / "project"
        self.project.mkdir()

    def _by_name(self, results, name):
        return next(r for r in results if r.name == name)

    def test_mcp_entries_pass_when_both_clients_aligned(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}},
        )
        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "claude-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "opencode-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "PASS")

    def test_mcp_entries_fail_when_clients_drift(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "C:/a"]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "claude-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "opencode-mcp-entry").status, "FAIL")
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "SKIP")

        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "C:/b"]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "FAIL")

    def test_skills_mirror_detects_drift(self) -> None:
        canonical = self.project / "skills" / "generate-brd"
        mirror = self.project / ".opencode" / "skills" / "generate-brd"
        canonical.mkdir(parents=True)
        mirror.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("v2", encoding="utf-8")
        (mirror / "SKILL.md").write_text("v1", encoding="utf-8")
        results = check_skills_mirror(self.project)
        self.assertEqual(results[0].status, "FAIL")
        self.assertIn("generate-brd", results[0].detail)

    def test_harness_check_main_returns_zero_when_checks_pass(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}},
        )
        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}},
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = harness_check_main(self.project)

        self.assertEqual(exit_code, 0)
        self.assertIn("PASS", stdout.getvalue())

    def test_harness_check_main_returns_nonzero_when_any_check_fails(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "C:/a"]}}},
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = harness_check_main(self.project)

        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL", stdout.getvalue())


class InstallerWriteGrantTests(unittest.TestCase):
    """T1-16: regression guard — both installers grant write=True to all sub-agents."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    def test_install_opencode_sh_grants_write_to_all_subagents(self) -> None:
        sh_path = self.REPO_ROOT / "install-opencode.sh"
        if not sh_path.exists():
            self.skipTest("install-opencode.sh not found")
        content = sh_path.read_text(encoding="utf-8")
        self.assertIn(
            '"write": True',
            content,
            "install-opencode.sh must grant write: True to sub-agents",
        )

    def test_install_opencode_ps1_grants_write_to_all_subagents(self) -> None:
        ps1_path = self.REPO_ROOT / "install-opencode.ps1"
        if not ps1_path.exists():
            self.skipTest("install-opencode.ps1 not found")
        content = ps1_path.read_text(encoding="utf-8")
        self.assertIn(
            "write = $true",
            content,
            "install-opencode.ps1 must grant write = $true to sub-agents",
        )


if __name__ == "__main__":
    unittest.main()
