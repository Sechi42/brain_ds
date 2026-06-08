import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
RENDERER = ROOT / "brain_ds" / "ui" / "src" / "renderer.ts"


class TestGraphReadabilityControlsPR3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_text = TEMPLATE.read_text(encoding="utf-8")
        cls.renderer_text = RENDERER.read_text(encoding="utf-8")

    def test_edge_width_scale_field_and_setter_exist(self):
        self.assertIn("this._edgeWidthScale", self.renderer_text)
        self.assertRegex(self.renderer_text, r"setEdgeWidthScale\s*=\s*function")

    def test_edge_width_scale_applies_in_draw_edges(self):
        # Floor lowered from 1 to 0.25 so the slider can render genuinely thinner
        # edges (live-usability follow-up); sub-0.25 is clamped to keep edges visible.
        self.assertRegex(
            self.renderer_text,
            r"ctx\.lineWidth\s*=\s*Math\.max\(0\.25,\s*Number\(edge\.width\s*\|\|\s*edge\.value\s*\|\|\s*1\)\s*\*\s*self\._edgeWidthScale\)",
        )

    def test_label_weight_field_and_setter_exist(self):
        self.assertIn("this._labelFontWeight", self.renderer_text)
        self.assertRegex(self.renderer_text, r"setLabelFontWeight\s*=\s*function")

    def test_label_weight_applies_in_font_string(self):
        self.assertRegex(
            self.renderer_text,
            r"ctx\.font\s*=\s*String\(self\._labelFontWeight\)\s*\+\s*\"\s+12px sans-serif\"",
        )

    def test_left_panel_has_edge_thickness_control(self):
        self.assertIn('id="edge-thickness-slider"', self.template_text)
        self.assertIn('aria-label="Grosor de aristas"', self.template_text)

    def test_left_panel_has_label_weight_control(self):
        self.assertIn('id="label-weight-control"', self.template_text)
        self.assertIn('aria-label="Peso de etiquetas"', self.template_text)
