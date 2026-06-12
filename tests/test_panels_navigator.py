import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
WORKSPACE_CHROME = ROOT / "brain_ds" / "ui" / "src" / "workspace-chrome.ts"


class TestPR4NavigatorContracts(unittest.TestCase):
    """PR4 contracts for navigator panel + same-node deselect."""

    def test_navigator_panel_exists_with_heading(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn('<section class="panel-card" data-accordion-section="navigator"', src)
        self.assertIn('navigator panel-card removed: see Proyectos section for equivalent functionality', src)

    def test_navigator_mount_uses_select_and_reveal(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("const navigatorPanelEl = document.getElementById(\"navigator-panel\")", src)
        self.assertIn("const renderNavigatorPanel = () =>", src)
        self.assertIn("selectAndReveal(nodeId)", src)

    def test_navigator_groups_are_collapsible_and_keyboard_operable(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('setAttribute("aria-expanded"', src)
        self.assertIn('toggle.addEventListener("click"', src)
        self.assertIn('toggle.addEventListener("keydown"', src)
        self.assertIn('event.key === "Enter"', src)

    def test_navigator_uses_render_context_data_not_hardcoded(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Array.isArray(typeGroups)", src)
        self.assertIn("group.types", src)
        self.assertIn("nodeTypeNames", src)
        self.assertIn("nodesByType", src)

    def test_navigator_panel_and_left_controls_are_scroll_contained(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(src, r"\.left-panel-shell\s+\.controls\s*\{[\s\S]*overflow-y:\s*auto;")
        self.assertRegex(src, r"#navigator-panel\s*\{[\s\S]*overflow-y:\s*auto;")

    def test_same_node_click_clears_selection_contract(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(
            src,
            r"network\.on\(\"click\",\s*\(params\)\s*=>\s*\{[\s\S]*?"
            r"if\s*\(clickedNodeId\s*!==\s*selectedNodeId\)\s*\{[\s\S]*?focusNode\(clickedNodeId\);[\s\S]*?\}"
            r"\s*else\s*\{[\s\S]*?clearSelectionState\(\);",
        )

    def test_workspace_chrome_includes_navigator_rail_mapping(self):
        src = WORKSPACE_CHROME.read_text(encoding="utf-8")
        self.assertIn('const RAIL_NAMES = ["file-tree", "search", "filters", "hierarchy", "layout"] as const;', src)
        self.assertIn('"layout": new Set(["layout"])', src)
        self.assertNotIn('"navigator": new Set(["navigator"])', src)


if __name__ == "__main__":
    unittest.main()
