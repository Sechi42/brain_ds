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

    def test_ai_actions_receipts_contract(self) -> None:
        text = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn('id="ai-actions-receipts"', text)
        self.assertIn("receipt-ok", text)
        self.assertIn("receipt-error", text)

    def test_live_sync_receipt_immediate_render_and_focus_contract(self) -> None:
        text = LIVE_SYNC_TS.read_text(encoding="utf-8")
        self.assertIn("tool.invoked", text)
        self.assertIn("onReceipt", text)
        self.assertIn("document.getElementById('ai-actions-receipts')", text)
        self.assertIn("focus({ preventScroll: true })", text)

    def test_live_sync_highlight_contract(self) -> None:
        text = LIVE_SYNC_TS.read_text(encoding="utf-8")
        self.assertIn("data-highlight", text)
        self.assertIn("removeAttribute('data-highlight')", text)
        self.assertIn("window.setTimeout", text)

    def test_viewer_reduced_motion_highlight_contract(self) -> None:
        text = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", text)
        self.assertIn("[data-highlight] .node-circle", text)
        self.assertIn("animation: none", text)


if __name__ == "__main__":
    unittest.main()
