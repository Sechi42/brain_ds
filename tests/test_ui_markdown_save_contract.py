from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPLIT_PANE_TS = ROOT / "brain_ds" / "ui" / "src" / "panels" / "split-pane.ts"
BRD_PANEL_TS = ROOT / "brain_ds" / "ui" / "src" / "panels" / "brd-panel.ts"
DETAIL_PANEL_TS = ROOT / "brain_ds" / "ui" / "src" / "panels" / "detail-panel.ts"
LIVE_SYNC_TS = ROOT / "brain_ds" / "ui" / "src" / "live" / "live-sync.ts"
VIEWER_HTML = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestUiMarkdownSaveContracts(unittest.TestCase):
    def test_split_pane_pins_reader_markdown_to_explicit_node_id(self) -> None:
        text = SPLIT_PANE_TS.read_text(encoding="utf-8")
        self.assertIn("getMarkdown?: (nodeId?: string | null) => string", text)
        self.assertIn("saveMarkdown?: (markdown: string, nodeId?: string | null) => Promise<boolean>", text)
        self.assertIn("_deps.getMarkdown(nodeId)", text)
        self.assertIn("const editingNodeId = _currentNodeId", text)
        self.assertIn("_deps.saveMarkdown(textarea.value, editingNodeId)", text)

    def test_split_pane_closes_notes_editor_in_place_after_blur(self) -> None:
        text = SPLIT_PANE_TS.read_text(encoding="utf-8")
        self.assertIn("function appendNotesView(nodeId: string, container: HTMLElement, statusEl: HTMLSpanElement): void", text)
        self.assertIn("const closeEditor = () => {", text)
        self.assertIn("if (!container.isConnected) return;", text)
        self.assertIn("appendNotesView(nodeId, container, statusEl);", text)
        self.assertIn("if (textarea.value === getNotesForNode(nodeId))", text)
        self.assertIn("doSave().then(() => closeEditor())", text)

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

    def test_viewer_reader_toolbar_sticky_flush_contract(self) -> None:
        text = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn("top: -1.5rem", text)
        self.assertIn("margin: -1.5rem -2rem 0.75rem", text)
        self.assertIn("padding: 1rem 2rem 0.6rem", text)

    def test_viewer_reader_allows_adding_content_from_empty_state(self) -> None:
        text = SPLIT_PANE_TS.read_text(encoding="utf-8")
        self.assertIn("raw ? 'Editar' : 'Agregar contenido'", text)

    def test_brd_panel_summary_and_full_reader_contract(self) -> None:
        panel_text = BRD_PANEL_TS.read_text(encoding="utf-8")
        template_text = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn("brd-panel-summary", panel_text)
        self.assertIn("Abrir BRD completo", panel_text)
        self.assertIn("function extractPreview(markdown: string): string", panel_text)
        self.assertIn("title: \"Contenido\"", template_text)
        self.assertIn("nodeId || window.brainDsUI.detailPanel.getSelectedNodeId()", template_text)


if __name__ == "__main__":
    unittest.main()
