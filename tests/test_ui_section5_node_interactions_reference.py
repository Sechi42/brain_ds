import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SECTION_5_HTML = SECTIONS_DIR / "section-5-node-interactions.html"
SHELL_MD = SECTIONS_DIR / "ui-workspace-shell.md"
GRAPH_VIEWER_HTML = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
RENDERER_TS = ROOT / "brain_ds" / "ui" / "src" / "renderer.ts"


class TestUiSection5NodeInteractionsReference(unittest.TestCase):
    def test_static_reference_exists_and_isolation_contract(self):
        self.assertTrue(SECTION_5_HTML.exists(), "section-5-node-interactions.html must exist")
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('<link rel="stylesheet" href="_tokens.css"', html)
        self.assertIn('<link rel="stylesheet" href="_shared.css"', html)
        self.assertIn("Static design reference only", html)
        self.assertIn("renderer.ts is production implementation", html)
        self.assertNotRegex(html, r"<script\\b")
        self.assertNotIn("viewer.bundle.js", html)
        self.assertNotIn("type=\"module\"", html)

    def test_token_discipline_and_no_hardcoded_hex_in_section_styles(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")
        style_blocks = re.findall(r"<style>(.*?)</style>", html, flags=re.DOTALL)
        self.assertGreaterEqual(len(style_blocks), 1)
        styles = "\n".join(style_blocks)

        self.assertNotRegex(styles, r"#[0-9a-fA-F]{3,8}")
        self.assertGreaterEqual(len(re.findall(r"var\(--[a-z0-9\-]+\)", styles)), 20)

    def test_all_panels_and_state_contracts(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        expected_states = [
            "default",
            "hover",
            "hover-popover",
            "selected",
            "keyboard-focus",
            "ego-dimming",
            "marquee",
            "edge-states",
            "context-menu",
        ]
        for state in expected_states:
            self.assertIn(f'data-node-state="{state}"', html)

        self.assertEqual(len(re.findall(r'class="panel"', html)), 9)
        self.assertGreaterEqual(len(re.findall(r'data-status="shipped"', html)), 7)
        self.assertGreaterEqual(len(re.findall(r'data-status="proposed"', html)), 1)

        # each panel must expose an implementation sync reference
        self.assertGreaterEqual(len(re.findall(r"(renderer\.ts:[0-9]+|context-menu\.ts:[0-9]+)", html)), 9)

    def test_relationship_neighborhood_and_ego_dimming_contract(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('data-node-state="ego-dimming"', html)
        self.assertIn('data-hop="0"', html)
        self.assertGreaterEqual(len(re.findall(r'data-hop="1"', html)), 1)
        self.assertGreaterEqual(len(re.findall(r'data-hop="2"', html)), 1)
        self.assertGreaterEqual(len(re.findall(r'data-node-role="dimmed"', html)), 1)
        self.assertIn("Hover dimming SHIPPED", html)
        self.assertIn("Selection dimming PROPOSED", html)

    def test_marquee_multiselect_and_context_menu_contract(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('data-node-state="marquee"', html)
        self.assertIn('data-select-state="multi-selected"', html)
        self.assertIn('class="marquee-rect"', html)
        self.assertIn("selectedNodeIds Set", html)

        self.assertIn('data-node-state="context-menu"', html)
        self.assertIn('class="context-menu"', html)
        self.assertIn("Arrow / Esc", html)
        self.assertIn("score-filter", html)

    def test_edge_relationship_contract(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('data-node-state="edge-states"', html)
        self.assertIn('data-edge-state="default"', html)
        self.assertIn('data-edge-state="hover-related"', html)
        self.assertIn('data-edge-state="dimmed"', html)

    def test_demarcation_every_panel_has_status_chip_and_sync_reference(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        panel_blocks = re.findall(r'(<section class="panel".*?</section>)', html, flags=re.DOTALL)
        self.assertEqual(len(panel_blocks), 9)
        for block in panel_blocks:
            self.assertRegex(block, r'data-status="(shipped|proposed)"')
            self.assertRegex(block, r'(renderer\.ts:[0-9]+|context-menu\.ts:[0-9]+)')

    def test_hover_visual_direction_uses_gray_rest_and_purple_related_state(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn("Futuristic Obsidian-gray rest state", html)
        self.assertIn('data-node-role="hover-target"', html)
        self.assertGreaterEqual(len(re.findall(r'data-edge-state="related"', html)), 2)
        self.assertIn("node-hover-breathe", html)

        style_blocks = re.findall(r"<style>(.*?)</style>", html, flags=re.DOTALL)
        styles = "\n".join(style_blocks)
        self.assertIn("background: var(--bg-active);", styles)
        self.assertIn("background: var(--accent-mora);", styles)
        self.assertIn("transform: scale(1.22);", styles)

    def test_selected_visual_direction_locks_clicked_node_and_related_surfaces(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('data-node-role="selected-target"', html)
        self.assertGreaterEqual(len(re.findall(r'data-node-role="selected-connection"', html)), 2)
        self.assertGreaterEqual(len(re.findall(r'data-edge-state="selected-related"', html)), 2)
        self.assertIn("Clicked node locks full purple", html)

        style_blocks = re.findall(r"<style>(.*?)</style>", html, flags=re.DOTALL)
        styles = "\n".join(style_blocks)
        self.assertIn("[data-node-state='selected'] .mock-node[data-node-role='selected-target']", styles)
        self.assertIn("[data-node-state='selected'] .mock-node[data-node-role='selected-connection']", styles)
        self.assertIn("background: var(--accent-mora);", styles)
        self.assertIn("box-shadow: inset 0 0 0 1px var(--accent-mora);", styles)

    def test_hover_popover_contract_explicit_panel(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")

        self.assertIn('data-node-state="hover-popover"', html)
        self.assertIn('class="hover-popover"', html)
        self.assertIn('data-node-role="popover-anchor"', html)
        # Popover surface must expose a preview card contract: title, score, neighbors
        self.assertRegex(html, r'class="hover-popover-title"')
        self.assertRegex(html, r'class="hover-popover-meta"')
        # Tether/leader line connecting anchor to popover
        self.assertIn('class="hover-popover-tether"', html)
        # Popover panel must use only token variables, never raw hex
        style_blocks = re.findall(r"<style>(.*?)</style>", html, flags=re.DOTALL)
        styles = "\n".join(style_blocks)
        self.assertIn(".hover-popover", styles)
        self.assertIn("var(--vis-panel-bg)", styles)
        self.assertIn("var(--vis-panel-border)", styles)
        # Animated reveal must be defined for the popover
        self.assertIn("@keyframes popover-reveal", styles)
        # Documentation contract must explicitly list hover-popover
        shell_doc = SHELL_MD.read_text(encoding="utf-8")
        self.assertIn("hover-popover", shell_doc)

    def test_workspace_shell_has_node_interaction_visual_contracts_slice(self):
        content = SHELL_MD.read_text(encoding="utf-8")
        self.assertIn("## Node Interaction Visual Contracts", content)
        self.assertIn("Section 5 (slice 2)", content)
        self.assertIn("default", content)
        self.assertIn("hover", content)
        self.assertIn("selected", content)
        self.assertIn("keyboard-focus", content)
        self.assertIn("ego-dimming", content)
        self.assertIn("marquee + multi-select", content)
        self.assertIn("edge-states", content)
        self.assertIn("context menu + score-filter affordance", content)
        self.assertIn("No new token families", content)

    def test_out_of_scope_cross_reference_points_to_section5_design_only_contract(self):
        content = SHELL_MD.read_text(encoding="utf-8")
        self.assertIn("See \"Node Interaction Visual Contracts\" below for design-only mappings.", content)

    def test_production_isolation_section5_not_wired_into_runtime(self):
        html = SECTION_5_HTML.read_text(encoding="utf-8")
        shell_doc = SHELL_MD.read_text(encoding="utf-8")
        production_template = GRAPH_VIEWER_HTML.read_text(encoding="utf-8")
        production_renderer = RENDERER_TS.read_text(encoding="utf-8")

        self.assertIn("Static design reference only", html)
        self.assertIn("design-only and never loaded by production runtime", shell_doc)
        self.assertNotIn("section-5-node-interactions.html", production_template)
        self.assertNotIn("section-5-node-interactions.html", production_renderer)


if __name__ == "__main__":
    unittest.main()
