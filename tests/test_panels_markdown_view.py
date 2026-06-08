import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
SPLIT_PANE = ROOT / "brain_ds" / "ui" / "src" / "panels" / "split-pane.ts"


class TestMarkdownFullPanelReaderPR3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_text = TEMPLATE.read_text(encoding="utf-8")
        cls.split_text = SPLIT_PANE.read_text(encoding="utf-8")

    def test_reader_trigger_is_prominent_pill_button(self):
        self.assertRegex(
            self.template_text,
            r'id="show-more"[^>]*class="[^"]*pill-btn',
            "show-more control must use .pill-btn for accessible prominence",
        )

    def test_center_split_supports_reader_layout_state(self):
        self.assertIn("root.setAttribute('data-layout', 'reader')", self.split_text)
        self.assertRegex(
            self.template_text,
            r'#center-split\[data-layout="reader"\]',
            "Template CSS must define reader layout behavior",
        )

    def test_escape_handler_returns_to_previous_layout(self):
        self.assertIn("event.key === 'Escape'", self.split_text)
        self.assertIn("root.setAttribute('data-layout', previousLayout)", self.split_text)

    def test_focus_restores_to_trigger_when_reader_closes(self):
        self.assertIn("lastTrigger", self.split_text)
        self.assertIn("lastTrigger.focus", self.split_text)

    def test_show_does_not_force_detail_edit_mode(self):
        self.assertNotIn("setEditMode(true)", self.split_text)
