"""Contract tests for the live-graph-workspace usability follow-up round.

Covers the user-reported fixes after the PR1-PR4 cycle:
  - navigator visual refresh + globe icon + type-color dots
  - edges/labels can be made thinner (slider floor lowered, Fina weight)
  - inspector Export JSON enabled on selection (not gated on edits)
  - node deselection via Escape + empty-canvas backdrop click
  - node drag in overlay mode (canvas host is pointer-events:none) with
    neighbor re-settling and drop-to-fix

These are source-contract assertions: the live behaviour is validated with
Playwright separately, but these lock the implementation so a regression is caught
by the unittest suite.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
RENDERER = ROOT / "brain_ds" / "ui" / "src" / "renderer.ts"
RENDERER_D4 = ROOT / "brain_ds" / "ui" / "src" / "renderer-d4.ts"
DETAIL_PANEL = ROOT / "brain_ds" / "ui" / "src" / "panels" / "detail-panel.ts"
ICONS_DIR = ROOT / "brain_ds" / "ui" / "assets" / "icons"
SPRITE = ROOT / "brain_ds" / "ui" / "assets" / "icons.sprite.svg"


class TestNavigatorRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_navigator_rail_and_title_use_globe_icon(self):
        # Navigator is intentionally removed; Projects/file-tree absorbs that role.
        self.assertNotIn('data-rail-icon="navigator"', self.template)
        self.assertIn('data-rail-icon="file-tree"', self.template)
        self.assertIn('navigator panel-card removed', self.template)

    def test_globe_icon_source_and_sprite_exist(self):
        self.assertTrue((ICONS_DIR / "globe.svg").exists(), "globe.svg source icon must exist")
        self.assertIn('id="icon-globe"', SPRITE.read_text(encoding="utf-8"))

    def test_navigator_node_rows_render_type_color_dot(self):
        self.assertIn("navigator-node-dot", self.template)
        self.assertIn("--navigator-dot-color", self.template)
        # Dot colour is resolved from the same per-node colour map the canvas uses.
        self.assertRegex(self.template, r'navigator-node-dot[\s\S]*?d4ColorVars\(node\)')

    def test_navigator_group_header_has_count_and_chevron(self):
        self.assertIn("navigator-group-count", self.template)
        self.assertIn("navigator-chevron", self.template)

    def test_navigator_node_button_keeps_44px_hit_target(self):
        self.assertRegex(
            self.template,
            r'\.navigator-node-btn\s*\{[^}]*min-height:\s*44px',
        )


class TestThinnerEdgesAndLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.renderer = RENDERER.read_text(encoding="utf-8")

    def test_edge_slider_allows_sub_one_minimum(self):
        self.assertRegex(self.template, r'id="edge-thickness-slider"[\s\S]*?min="0\.25"')

    def test_canvas_edge_floor_lowered_to_quarter(self):
        self.assertRegex(self.renderer, r"ctx\.lineWidth\s*=\s*Math\.max\(0\.25,")

    def test_label_weight_offers_lighter_fina_option(self):
        self.assertIn('data-label-weight="300"', self.template)
        self.assertRegex(self.template, r'data-label-weight="300">Fina<')


class TestExportGating(unittest.TestCase):
    def test_export_enabled_on_selection_not_on_edits(self):
        text = DETAIL_PANEL.read_text(encoding="utf-8")
        self.assertIn("_exportJsonBtn.disabled = !hasSelection;", text)
        self.assertNotIn("_exportJsonBtn.disabled = !_hasEdits;", text)


class TestDeselection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_escape_clears_selection_outside_text_fields(self):
        self.assertRegex(
            self.template,
            r'addEventListener\("keydown",\s*\(event\)\s*=>\s*\{[\s\S]*?event\.key\s*!==\s*"Escape"[\s\S]*?'
            r'INPUT[\s\S]*?clearSelectionState\(\);',
        )

    def test_backdrop_click_clears_selection(self):
        self.assertRegex(
            self.template,
            r'centerCanvasContainer\.addEventListener\("click"[\s\S]*?onInteractive[\s\S]*?clearSelectionState\(\);',
        )


class TestNodeDragOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d4 = RENDERER_D4.read_text(encoding="utf-8")
        cls.renderer = RENDERER.read_text(encoding="utf-8")

    def test_overlay_node_has_pointer_drag(self):
        self.assertIn("addEventListener('pointerdown'", self.d4)
        self.assertIn("network.dragNodeId = node.id", self.d4)
        self.assertIn("network._screenToWorld(", self.d4)

    def test_drag_reheats_and_fixes_on_drop(self):
        self.assertRegex(self.d4, r"network\.temperature\s*=\s*Math\.max\(")
        self.assertIn("live.fixed = true", self.d4)

    def test_applyforces_pins_dragged_and_fixed_nodes(self):
        self.assertRegex(
            self.renderer,
            r"if\s*\(a\.fixed\s*\|\|\s*\(this\.dragNodeId\s*!==\s*null",
        )


if __name__ == "__main__":
    unittest.main()
