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

    def test_readme_mentions_twenty_four_tools(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("24 tools", readme)
        self.assertNotIn("22 tools", readme)

    def test_install_mentions_twenty_four_tools(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("24 tools", install)
        self.assertNotIn("22 tools", install)

    def test_install_covers_workspace_secret_cli(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("brain_ds secret", install)
        self.assertIn("secret list", install)
        self.assertIn("secret add", install)
        self.assertIn("secret remove", install)
        self.assertIn("secret validate", install)

    def test_install_covers_manual_manifest_edit(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn(".brain_ds/secrets.json", install)
        self.assertIn("schema", install)
        self.assertIn("fail-closed", install)

    def test_install_covers_provider_kinds(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        for kind in ("postgres", "sqlserver", "aws-secrets", "google-sheets-json"):
            self.assertIn(kind, install)

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


if __name__ == "__main__":
    unittest.main()
