from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAPH_VIEWER = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestRailPanelsC(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = GRAPH_VIEWER.read_text(encoding="utf-8")

    def test_right_panel_uses_single_set_active_dispatcher(self) -> None:
        self.assertIn("const setActiveRightPanel", self.html)
        self.assertRegex(self.html, r"setActiveRightPanel\(['\"]brd['\"]\)")
        self.assertRegex(self.html, r"setActiveRightPanel\(['\"]settings['\"]\)")

    def test_rail_panels_have_isolation_and_hidden_override(self) -> None:
        for selector in ("#brd-panel", "#secret-panel", ".inspector-stub-scroll"):
            self.assertRegex(
                self.html,
                rf"{re.escape(selector)}\s*\{{[^}}]*isolation:\s*isolate;[^}}]*contain:\s*layout;",
            )
        self.assertRegex(
            self.html,
            r"\.right-panel-shell\s+#brd-panel\[hidden\],\s*\.right-panel-shell\s+#secret-panel\[hidden\],\s*\.right-panel-shell\s+\.inspector-stub-scroll\[hidden\]\s*\{[^}]*display:\s*none\s*!important;",
        )

    def test_secret_panel_is_card_sized(self) -> None:
        self.assertRegex(self.html, r"#secret-panel\s*\{[^}]*max-width:")
        self.assertRegex(self.html, r"#secret-panel\s*\{[^}]*align-self:")
