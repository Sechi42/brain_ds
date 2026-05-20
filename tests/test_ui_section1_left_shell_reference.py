import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SECTION_1_HTML = SECTIONS_DIR / "section-1-left-shell.html"
SECTION_2_HTML = SECTIONS_DIR / "section-2-right-shell.html"
SHELL_MD = SECTIONS_DIR / "ui-workspace-shell.md"


class TestUiSection1LeftShellReference(unittest.TestCase):
    def test_section_1_html_contract_and_rail_semantics(self):
        self.assertTrue(SECTION_1_HTML.exists(), "section-1-left-shell.html must exist")
        html = SECTION_1_HTML.read_text(encoding="utf-8")

        self.assertIn('data-rail-side="left"', html)
        self.assertNotIn('aria-current="page"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertGreaterEqual(len(re.findall(r'data-rail-icon="', html)), 4)

        # Compact rail icon rule: 18×18 glyphs on 44×44 targets.
        self.assertIn('.rail-icon svg', html)
        self.assertIn('width: 18px;', html)
        self.assertIn('height: 18px;', html)

    def test_markdown_neutral_examples_and_aria_selected_only(self):
        self.assertTrue(SHELL_MD.exists(), "ui-workspace-shell.md must exist")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("## Section 1 — Left Rail, Content Panel, Status Chip", content)
        self.assertNotIn("aria-current=\"page\"", content)
        self.assertIn("aria-selected=\"true\"", content)

        # Neutral naming contract: no legacy YSGA placeholders in current examples.
        self.assertNotIn("YSGA", content)
        self.assertIn("Acme", content)

    def test_right_rail_semantics_also_uses_aria_selected_only(self):
        self.assertTrue(SECTION_2_HTML.exists(), "section-2-right-shell.html must exist")
        html = SECTION_2_HTML.read_text(encoding="utf-8")
        self.assertNotIn('aria-current="page"', html)
        self.assertIn('aria-selected="true"', html)

    def test_left_panel_routing_file_tree_and_single_active_module(self):
        html = SECTION_1_HTML.read_text(encoding="utf-8")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("mount(root, deps)", content)
        self.assertIn("unmount()", content)
        for icon_id in ["file-tree", "search", "filters", "hierarchy", "layout"]:
            self.assertIn(f"| `{icon_id}` |", content)

        self.assertIn('data-panel-module="file-tree"', html)
        self.assertEqual(len(re.findall(r'data-panel-module="', html)), 1)

    def test_file_tree_component_contract_and_mock_data_shape(self):
        html = SECTION_1_HTML.read_text(encoding="utf-8")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("interface TreeNode", content)
        self.assertIn("id: string", content)
        self.assertIn("displayPath: string", content)
        self.assertIn('type: "project" | "graph"', content)
        self.assertIn("children?: TreeNode[]", content)
        self.assertIn("onProjectSelect(projectId: string): void", content)
        self.assertIn("onGraphOpen(graphRef: { id: string; displayPath: string }): void", content)

        project_nodes = re.findall(r'data-node-type="project"', html)
        graph_nodes = re.findall(r'data-node-type="graph"', html)
        self.assertGreaterEqual(len(project_nodes), 2)
        self.assertGreaterEqual(len(graph_nodes), 2)
        self.assertNotIn("C:/", html)
        self.assertNotIn("\\\\", html)

    def test_left_accordion_status_chip_and_tokens_contracts(self):
        html = SECTION_1_HTML.read_text(encoding="utf-8")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("data-accordion-section", content)
        self.assertIn("data-accordion-open", content)
        self.assertIn("aria-expanded=\"true|false\"", content)
        self.assertIn('data-accordion-section="vaults"', html)
        self.assertIn('data-accordion-open="true"', html)
        self.assertIn('aria-expanded="true"', html)

        self.assertIn("Status Chip Contract (L-6)", content)
        self.assertIn("RENDER_CONTEXT.meta.org", content)
        self.assertIn("max 4 uppercase chars", content)
        self.assertRegex(html, r'data-status-chip="[^"]+">[A-Z]{1,4}</button>')
        self.assertRegex(html, r'data-rail-side="left"[\s\S]*data-status-chip="')

        self.assertIn("Token Mapping (L-7)", content)
        for token in ["--bg-panel", "--bg-panel-hover", "--bg-active", "--border-subtle", "--text-normal", "--accent-mora"]:
            self.assertIn(f"`{token}`", content)


if __name__ == "__main__":
    unittest.main()
