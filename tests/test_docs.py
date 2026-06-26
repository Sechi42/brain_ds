"""Lightweight guards for human-facing docs staying in sync with the implementation.

These tests do not exhaustively validate prose style; they assert that key
operational facts (tool count, feature coverage) are documented so installers
and operators are not misled.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProjectDocsCoverageTests(unittest.TestCase):
    """Guards for README.md and INSTALL.md coverage."""

    def test_readme_mentions_thirty_one_tools(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("31 tools", readme)
        self.assertNotIn("30 tools", readme)
        self.assertNotIn("29 tools", readme)
        self.assertNotIn("24 tools", readme)
        self.assertNotIn("22 tools", readme)

    def test_readme_mcp_table_includes_all_graph_tools(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for tool in ("assess_completeness", "get_weak_edges", "snapshot_edges"):
            self.assertIn(tool, readme)

    def test_readme_promotes_onboard_as_install_front_door(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("brain_ds onboard", readme)
        self.assertIn("setup + install-opencode", readme)
        self.assertIn("advanced/compat", readme)

    def test_install_mentions_thirty_one_tools(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("31 tools", install)
        self.assertNotIn("30 tools", install)
        self.assertNotIn("29 tools", install)
        self.assertNotIn("24 tools", install)
        self.assertNotIn("22 tools", install)

    def test_install_promotes_onboard_as_install_front_door(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")

        self.assertIn("brain_ds onboard", install)
        self.assertIn("setup + install-opencode", install)
        self.assertIn("compatibilidad avanzada", install)

    def test_install_covers_workspace_secret_cli(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("brain_ds secret", install)
        self.assertIn("secret list", install)
        self.assertIn("secret add", install)
        self.assertIn("secret remove", install)
        self.assertIn("secret validate", install)

    def test_install_uses_correct_secret_add_flags(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("--value-env", install)
        self.assertIn("--value-file", install)
        self.assertIn("--value-stdin", install)
        self.assertIn("--metadata-json", install)
        self.assertNotIn("--env-var", install)
        self.assertNotIn("--file", install)

    def test_install_covers_manual_manifest_edit(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn(".brain_ds/secrets.json", install)
        self.assertIn("schema", install)
        self.assertIn("fail-closed", install)

    def test_install_covers_provider_kinds(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        for kind in ("postgres", "sqlserver", "aws-secrets", "google-sheets-json"):
            self.assertIn(kind, install)

    def test_install_covers_secret_ref_for_database_kinds(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("secret_ref", install)
        # Both postgres and sqlserver metadata rows should mention secret_ref.
        lines = [line for line in install.splitlines() if "secret_ref" in line]
        self.assertGreaterEqual(len(lines), 2)

    def test_install_covers_probe_opt_in(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("--probe", install)
        self.assertIn("opt-in", install)

    def test_install_covers_ui_gear_panel(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("gear", install)
        self.assertIn("secret panel", install)

    def test_install_covers_security_invariants(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("redact", install)
        self.assertIn("crudos", install)
        self.assertIn("0600", install)

    def test_install_values_permission_does_not_overclaim_windows(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        # The doc must mention the POSIX 0600 guarantee and the Windows default-ACL caveat.
        self.assertIn("0600", install)
        self.assertIn("Windows", install)
        self.assertIn("ACL", install)


if __name__ == "__main__":
    unittest.main()
