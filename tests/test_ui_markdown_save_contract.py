from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DETAIL_PANEL_TS = ROOT / "brain_ds" / "ui" / "src" / "panels" / "detail-panel.ts"
LIVE_SYNC_TS = ROOT / "brain_ds" / "ui" / "src" / "live" / "live-sync.ts"
VIEWER_HTML = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestUiMarkdownSaveContracts(unittest.TestCase):
    def test_detail_panel_has_save_button_and_patch_contract(self) -> None:
        text = DETAIL_PANEL_TS.read_text(encoding="utf-8")
        self.assertIn("detail-save", text)
        self.assertIn("/api/nodes/", text)
        self.assertIn('method: "PATCH"', text)
        self.assertIn("graph_id", text)
        self.assertIn("changes", text)

    def test_live_sync_has_conflict_stale_contract(self) -> None:
        text = LIVE_SYNC_TS.read_text(encoding="utf-8")
        self.assertIn('data-conflict="stale"', text)
        self.assertIn("#detail-conflict-banner", text)

    def test_viewer_template_contains_conflict_banner(self) -> None:
        text = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn("detail-conflict-banner", text)


if __name__ == "__main__":
    unittest.main()
