import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SECTION_2_HTML = SECTIONS_DIR / "section-2-right-shell.html"
SHELL_MD = SECTIONS_DIR / "ui-workspace-shell.md"


class TestUiSection2RightShellReference(unittest.TestCase):
    def test_section_2_html_contract(self):
        self.assertTrue(SECTION_2_HTML.exists(), "section-2-right-shell.html must exist")
        html = SECTION_2_HTML.read_text(encoding="utf-8")

        self.assertIn('data-rail-side="right"', html)
        self.assertEqual(len(re.findall(r'data-rail-icon="', html)), 1)
        self.assertIn('data-rail-icon="gear"', html)
        self.assertNotIn('data-rail-icon="magic-wand"', html)
        self.assertIn('data-panel-module="settings"', html)

        expected_sections = ["properties", "metadata", "related", "ai-actions"]
        for section in expected_sections:
            self.assertIn(f'data-accordion-section="{section}"', html)

        self.assertNotIn('data-accordion-section="evidence"', html)
        self.assertIn('MCP bridge — not wired', html)

    def test_section_2_markdown_contract_not_stub(self):
        self.assertTrue(SHELL_MD.exists(), "ui-workspace-shell.md must exist")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("## Section 2 — Right Rail, Inspector Panel", content)
        self.assertNotIn("_Filled in by PR-3._", content)
        self.assertIn("data-rail-side=\"right\"", content)
        self.assertIn("data-panel-module=\"settings\"", content)
        self.assertIn("onAiAction(actionId: string, nodeId: string): void", content)

    def test_section_2_token_mapping_and_token_only_usage(self):
        html = SECTION_2_HTML.read_text(encoding="utf-8")
        content = SHELL_MD.read_text(encoding="utf-8")

        self.assertIn("### Token Mapping (R-6)", content)
        for token in [
            "--bg-panel",
            "--bg-panel-hover",
            "--bg-active",
            "--border-subtle",
            "--text-normal",
            "--text-bright",
            "--accent-mora",
        ]:
            self.assertIn(f"`{token}`", content)

        for hardcoded in ["#161616", "#1e1e1e", "#a78bfa"]:
            self.assertNotIn(hardcoded, html)
        self.assertIn("var(--bg-panel)", html)
        self.assertIn("var(--border-subtle)", html)


if __name__ == "__main__":
    unittest.main()
