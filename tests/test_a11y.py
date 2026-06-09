import unittest
from pathlib import Path

from brain_ds.ui.template_renderer import render_interactive_html


ROOT = Path(__file__).resolve().parent.parent
RENDERER_TS = ROOT / "brain_ds" / "ui" / "src" / "renderer.ts"
SEARCH_TS = ROOT / "brain_ds" / "ui" / "src" / "panels" / "search.ts"
CONTEXT_MENU_TS = ROOT / "brain_ds" / "ui" / "src" / "interactions" / "context-menu.ts"
VIEWER_TEMPLATE = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


def _sample_context():
    return {
        "meta": {"org": "A11y Org", "node_count": 2, "edge_count": 1, "generated_at": ""},
        "nodes": [
            {"id": "n1", "label": "Node One", "type": "Department"},
            {"id": "n2", "label": "Node Two", "type": "Role"},
        ],
        "edges": [{"from": "n1", "to": "n2", "label": "uses"}],
        "type_groups": [],
        "adjacency": {"n1": ["n2"], "n2": []},
    }


class TestA11ySlice9Contracts(unittest.TestCase):
    def test_initial_dom_contains_live_region(self):
        html = render_interactive_html(_sample_context())
        self.assertIn('id="viewer-live-region"', html)
        self.assertIn('aria-live="polite"', html)

    def test_icon_only_controls_have_accessible_names(self):
        html = render_interactive_html(_sample_context())
        for control_id in ("theme-toggle", "detail-collapse", "detail-close"):
            self.assertRegex(
                html,
                rf'id="{control_id}"[^>]*aria-label="[^"]+"',
                f"{control_id} must have a non-empty aria-label",
            )

    def test_search_clear_button_has_accessible_name_in_source(self):
        src = SEARCH_TS.read_text(encoding="utf-8")
        self.assertIn('aria-label", "Clear search"', src)

    def test_a11y_listbox_mirror_filters_to_visible_nodes(self):
        src = RENDERER_TS.read_text(encoding="utf-8")
        self.assertIn('setAttribute("role", "listbox")', src)
        self.assertIn("if (node.hidden) return;", src)
        self.assertIn("visibleNodes.push(node)", src)
        self.assertTrue(
            "this.a11yList.appendChild(li)" in src or "self.a11yList.appendChild(li)" in src,
            "Renderer must append one listbox option per visible node",
        )

    def test_context_menu_restores_focus_to_trigger_on_escape(self):
        src = CONTEXT_MENU_TS.read_text(encoding="utf-8")
        self.assertRegex(
            src,
            r"_contextMenuState\.target\s*=\s*document\.activeElement",
            "Context menu open path must store trigger element for focus restoration",
        )
        self.assertRegex(
            src,
            r"_contextMenuState\.target.*focus\(",
            "Closing context menu must restore focus to the trigger element",
        )

    def test_global_shortcuts_ignore_text_inputs_contract(self):
        src = VIEWER_TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(src, r"addEventListener\(\s*\"keydown\"")
        self.assertRegex(src, r"isContentEditable")
        self.assertRegex(src, r"tagName\s*===\s*\"INPUT\"")
        self.assertRegex(src, r"tagName\s*===\s*\"TEXTAREA\"")


if __name__ == "__main__":
    unittest.main()
