import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SECTION_4_HTML = SECTIONS_DIR / "section-4-center-canvas.html"
SECTION_1_HTML = SECTIONS_DIR / "section-1-left-shell.html"
SECTION_2_HTML = SECTIONS_DIR / "section-2-right-shell.html"
SECTION_3_HTML = SECTIONS_DIR / "section-3-button-catalog.html"
SHELL_MD = SECTIONS_DIR / "ui-workspace-shell.md"
SHARED_CSS = SECTIONS_DIR / "_shared.css"
TOKENS_CSS = SECTIONS_DIR / "_tokens.css"


class TestUiSection4CenterCanvasReference(unittest.TestCase):
    def test_section_4_html_contract_and_valid_tab_close_markup(self):
        self.assertTrue(SECTION_4_HTML.exists(), "section-4-center-canvas.html must exist")
        html = SECTION_4_HTML.read_text(encoding="utf-8")

        self.assertIn('class="tab-strip"', html)
        self.assertIn('data-toolbar-zone="nav"', html)
        self.assertIn('data-toolbar-zone="view"', html)
        self.assertIn('data-toolbar-zone="overflow"', html)
        self.assertIn('data-toolbar-zone="system-chrome"', html)

        # Invalid interactive nesting must be absent: no button.tab-close inside button.tab.
        self.assertNotRegex(
            html,
            r'<button[^>]*class="tab"[^>]*>(?:(?!</button>).)*<button[^>]*class="tab-close"',
        )

        # Close affordance still exists and is linked to tabs.
        self.assertGreaterEqual(len(re.findall(r'class="tab-close"', html)), 2)
        self.assertGreaterEqual(len(re.findall(r'data-tab-id="', html)), 1)

    def test_cross_cutting_static_artifact_constraints(self):
        html_files = sorted(SECTIONS_DIR.glob("section-*-*.html"))
        self.assertEqual(
            [p.name for p in html_files],
            [
                "section-1-left-shell.html",
                "section-2-right-shell.html",
                "section-3-button-catalog.html",
                "section-4-center-canvas.html",
                "section-5-node-interactions.html",
            ],
        )

        for file_path in html_files:
            html = file_path.read_text(encoding="utf-8")
            self.assertNotIn("viewer.bundle.js", html)
            self.assertIn('<link rel="stylesheet" href="_tokens.css"', html)
            self.assertIn('<link rel="stylesheet" href="_shared.css"', html)

        self.assertTrue(SHARED_CSS.exists(), "_shared.css must exist")
        shared_css = SHARED_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", shared_css)

    def test_canvas_preservation_and_layout_migration_contract(self):
        html = SECTION_4_HTML.read_text(encoding="utf-8")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("### Canvas Region (C-4) — Out of Scope", content)
        for locked in [
            "renderer.ts",
            "Viewport pan/zoom",
            "Marquee multi-select",
            "Ego-network dimming",
            "Hover popover",
            "Context menu",
        ]:
            self.assertIn(locked, content)

        self.assertIn('id="network"', html)
        self.assertIn("data-canvas-mount", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("type=\"module\"", html)
        self.assertNotIn("new Network(", html)

        self.assertIn("RECOMMENDATION", content)
        self.assertIn("not locked", content)
        self.assertIn("Zoom-fit", content)
        self.assertIn("Theme-toggle", content)
        self.assertIn("deferred to design phase", content)

        self.assertIn('data-toolbar-zone="view"', html)
        self.assertIn('data-migration-slot="zoom-fit"', html)
        self.assertIn('data-migration-slot="theme-toggle"', html)
        self.assertIn("demo-only", html)

    def test_full_workspace_grid_and_cross_cutting_accessibility_contracts(self):
        content = SHELL_MD.read_text(encoding="utf-8")
        self.assertIn("## Full Workspace Grid (X-1 Wireframe)", content)
        self.assertIn("icon rail | panel | 1fr | panel | icon rail", content)
        self.assertIn("Responsive / mobile", content)
        self.assertIn("deferred to the design phase", content)

        shared_css = SHARED_CSS.read_text(encoding="utf-8")
        self.assertIn(".workspace-shell", shared_css)
        self.assertIn("grid-template-columns", shared_css)

        html_1 = SECTION_1_HTML.read_text(encoding="utf-8")
        html_2 = SECTION_2_HTML.read_text(encoding="utf-8")
        html_3 = SECTION_3_HTML.read_text(encoding="utf-8")
        html_4 = SECTION_4_HTML.read_text(encoding="utf-8")
        for html in [html_1, html_2, html_3, html_4]:
            self.assertIn('<link rel="stylesheet" href="_tokens.css"', html)
            self.assertIn('<link rel="stylesheet" href="_shared.css"', html)
            self.assertRegex(html, r'aria-label="[^"]+"')

        # B-4: at least one aria-pressed toggle in each reference HTML.
        self.assertRegex(html_1, r'aria-pressed="(true|false)"')
        self.assertRegex(html_2, r'aria-pressed="(true|false)"')
        self.assertRegex(html_3, r'aria-pressed="(true|false)"')
        self.assertRegex(html_4, r'aria-pressed="(true|false)"')

        # X-2: token source file includes required root variables.
        # Phase D.1: `_tokens.css` is a forwarding @import shim; canonical
        # tokens live in `brain_ds/ui/static/tokens.css`. Assert the shim
        # forwards to canonical, then assert the canonical file contains the
        # locked root variables.
        shim_tokens = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn('@import url("../../static/tokens.css")', shim_tokens)
        canonical_tokens = (ROOT / "brain_ds" / "ui" / "static" / "tokens.css").read_text(encoding="utf-8")
        self.assertIn(":root", canonical_tokens)
        for token in ["--bg-main", "--bg-panel", "--accent-mora", "--text-normal", "--border-subtle"]:
            self.assertIn(token, canonical_tokens)

        # X-4: reduced-motion pattern targets transition and animation.
        self.assertIn("@media (prefers-reduced-motion: reduce)", shared_css)
        self.assertIn("animation-duration", shared_css)
        self.assertIn("transition-duration", shared_css)


if __name__ == "__main__":
    unittest.main()
