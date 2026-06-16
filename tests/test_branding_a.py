from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VAULT_PICKER = ROOT / "brain_ds" / "ui" / "templates" / "vault_picker.html"
GRAPH_VIEWER = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
TABS_TS = ROOT / "brain_ds" / "ui" / "src" / "tabs.ts"


class TestBrandingA(unittest.TestCase):
    def test_vault_picker_uses_brandsds_title_and_heading(self) -> None:
        html = VAULT_PICKER.read_text(encoding="utf-8")
        self.assertIn("<title>BrainDS — pick workspace</title>", html)
        self.assertIn("<h1 class=\"picker-title\">BrainDS</h1>", html)

    def test_graph_viewer_uses_brandsds_title(self) -> None:
        html = GRAPH_VIEWER.read_text(encoding="utf-8")
        self.assertIn("<title>BrainDS Graph Viewer</title>", html)

    def test_internal_brain_ds_keys_remain_unchanged(self) -> None:
        html = GRAPH_VIEWER.read_text(encoding="utf-8")
        tabs = TABS_TS.read_text(encoding="utf-8")
        self.assertIn('brain_ds.theme', html)
        self.assertIn('brain_ds.tabs', tabs)
