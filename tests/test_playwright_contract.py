"""Contracts for Playwright live-server wiring."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_SETUP = REPO_ROOT / "brain_ds" / "ui" / "e2e" / "global-setup.ts"
ECOSYSTEM_SPEC = REPO_ROOT / "brain_ds" / "ui" / "e2e" / "ecosystem.spec.ts"


class TestPlaywrightContracts(unittest.TestCase):
    def test_global_setup_exports_ecosystem_base_url(self) -> None:
        source = GLOBAL_SETUP.read_text(encoding="utf-8")
        self.assertIn('process.env.BRAIN_DS_ECOSYSTEM_URL = baseUrl;', source)

    def test_ecosystem_spec_prefers_runtime_override_before_7777_fallback(self) -> None:
        source = ECOSYSTEM_SPEC.read_text(encoding="utf-8")
        self.assertIn('process.env.BRAIN_DS_ECOSYSTEM_URL ?? `http://127.0.0.1:${DEMO_PORT}`', source)


if __name__ == "__main__":
    unittest.main()
