"""Tests for local harness parity helpers."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from brain_ds.harness_check import check_project_mcp_entries


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


if __name__ == "__main__":
    unittest.main()
