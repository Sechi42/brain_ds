import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SECTION_3_HTML = SECTIONS_DIR / "section-3-button-catalog.html"
SHELL_MD = SECTIONS_DIR / "ui-workspace-shell.md"


class TestUiSection3ButtonCatalogReference(unittest.TestCase):
    def test_section_3_html_contract(self):
        self.assertTrue(SECTION_3_HTML.exists(), "section-3-button-catalog.html must exist")
        html = SECTION_3_HTML.read_text(encoding="utf-8")

        required_ids = [
            "file-tree",
            "search",
            "filters",
            "hierarchy",
            "layout",
            "gear",
            "tab-new",
            "tab-close",
            "nav-back",
            "nav-forward",
            "overflow",
            "status-chip",
        ]
        for catalog_id in required_ids:
            self.assertIn(f'data-catalog-id="{catalog_id}"', html)

        for state in ["default", "hover", "active", "focus", "disabled"]:
            self.assertIn(f'data-state="{state}"', html)

        self.assertIn('aria-label="Open file tree panel"', html)
        self.assertIn('aria-label="Open settings panel"', html)
        self.assertIn('aria-label="Close tab"', html)
        self.assertIn('aria-label="Back"', html)
        self.assertIn('aria-label="Forward"', html)

        self.assertIn("Ctrl+1", html)
        self.assertIn("Cmd+1", html)
        self.assertIn("Ctrl+W", html)
        self.assertIn("Cmd+W", html)

        self.assertNotIn("😀", html)
        self.assertNotIn("linear-gradient", html)

    def test_section_3_markdown_contract_not_stub(self):
        self.assertTrue(SHELL_MD.exists(), "ui-workspace-shell.md must exist")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("## Section 3 — Button / Icon Catalog", content)
        self.assertNotIn("_Filled in by PR-4._", content)
        self.assertIn("Master Icon-Button Catalog", content)
        self.assertIn("Keyboard Shortcut Map", content)
        self.assertIn("Accessibility Contract", content)
        self.assertIn("`--bg-panel-hover`", content)
        self.assertIn("`--bg-active`", content)
        self.assertIn("`--accent-mora`", content)

        # At least 10 catalog rows in markdown table
        section_start = content.find("## Section 3 — Button / Icon Catalog")
        self.assertGreaterEqual(section_start, 0)
        section_content = content[section_start:]
        rows = re.findall(r"\|\s*`[a-z0-9\-]+`\s*\|", section_content)
        self.assertGreaterEqual(len(rows), 10)


if __name__ == "__main__":
    unittest.main()
