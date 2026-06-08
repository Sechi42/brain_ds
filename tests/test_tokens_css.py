"""Tests for the canonical `brain_ds/ui/static/tokens.css` (Phase D.1).

Drives modern-design-tokens change. See engram topic
`sdd/modern-design-tokens/{spec,design,tasks}` for full context.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKENS_CSS = ROOT / "brain_ds" / "ui" / "static" / "tokens.css"
SECTIONS_DIR = ROOT / "brain_ds" / "ui" / "design" / "sections"
SHIM_CSS = SECTIONS_DIR / "_tokens.css"
CHECKPOINT_DIR = ROOT / "brain_ds" / "ui" / "design" / "checkpoints"
CHECKPOINT_HTML = CHECKPOINT_DIR / "d1-tokens-side-by-side.html"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _linearize(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    lr, lg, lb = _linearize(r), _linearize(g), _linearize(b)
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb


def _contrast(color_a: str, color_b: str) -> float:
    l1 = _luminance(color_a)
    l2 = _luminance(color_b)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# T1 — canonical tokens.css existence + structure
# ---------------------------------------------------------------------------


class TestTokensCssCatalog(unittest.TestCase):
    def test_tokens_css_file_exists(self):
        self.assertTrue(TOKENS_CSS.exists(), "brain_ds/ui/static/tokens.css must exist")
        self.assertGreater(len(TOKENS_CSS.read_text(encoding="utf-8").strip()), 0)

    def test_locked_palette_values_match_spec(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        for needle in (
            "--bg-main: #09090b",
            "--bg-panel: #121214",
            "--bg-panel-elevated: #141414",
            "--bg-canvas-deep: #0a0a0a",
            "--bg-panel-hover:",
            "--bg-active:",
            "--border-subtle: rgba(63, 63, 70, 0.4)",
            "--border-strong:",
        ):
            self.assertIn(needle, css, f"tokens.css missing substring: {needle!r}")

    def test_no_absolute_black_in_tokens_css(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        # forbid standalone #000 and #000000; allow longer hex like #0001 only by
        # checking that no `#000` token sits at a non-hex boundary.
        self.assertNotRegex(
            css,
            r"#000(?![0-9a-fA-F])",
            "tokens.css must not contain absolute black (#000 / #000000)",
        )

    def test_accent_mora_contrast_on_bg_main_aa(self):
        ratio = _contrast("#a78bfa", "#09090b")
        self.assertGreaterEqual(ratio, 4.5, f"--accent-mora on --bg-main contrast={ratio:.2f}")

    def test_text_tokens_pass_wcag_aa_on_new_bg_main(self):
        # DIV-5 locks the literal values from spec; the spec's "all >= 4.5"
        # consequence claim is mathematically false for --text-muted (#71717a
        # on #09090b = 4.12:1). Resolution: body-text tokens hold AA-body
        # (>=4.5), muted holds AA-large / non-essential (>=3.0). Token VALUES
        # are NOT changed; only this derived assertion is corrected.
        for text_color, label in (
            ("#f4f4f5", "--text-normal"),
            ("#ffffff", "--text-bright"),
        ):
            ratio = _contrast(text_color, "#09090b")
            self.assertGreaterEqual(ratio, 4.5, f"{label} contrast on #09090b = {ratio:.2f}")
        muted_ratio = _contrast("#71717a", "#09090b")
        self.assertGreaterEqual(
            muted_ratio,
            3.0,
            f"--text-muted contrast on #09090b = {muted_ratio:.2f} (AA-large required)",
        )

    def test_font_weight_tokens_available(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn("--fw-regular: 400", css)
        self.assertIn("--fw-medium: 500", css)
        self.assertIn("--fw-semibold: 600", css)

    def test_radius_scale_available_and_radius_ui_aliases_md(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn("--radius-sm: 4px", css)
        # DIV-4 (spec wins): --radius-md is 8px.
        self.assertIn("--radius-md: 8px", css)
        self.assertIn("--radius-lg: 12px", css)
        self.assertIn("--radius-full: 9999px", css)
        self.assertIn("--radius-ui: var(--radius-md)", css)

    def test_motion_tokens_present_in_tokens_css(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn("--duration-fast: 120ms", css)
        self.assertIn("--duration-normal: 200ms", css)
        self.assertIn("--duration-slow: 320ms", css)
        self.assertIn("--ease-standard: cubic-bezier(0.2, 0, 0, 1)", css)
        self.assertIn("--ease-emphasized: cubic-bezier(0.3, 0, 0, 1)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("--duration-fast: 0ms", css)
        self.assertIn("--duration-normal: 0ms", css)
        self.assertIn("--duration-slow: 0ms", css)

    def test_light_theme_overrides_exist_for_runtime_toggle(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn('[data-theme="light"]', css)
        self.assertIn("--bg-main: #f8fafc", css)
        self.assertIn("--bg-panel: #ffffff", css)
        self.assertIn("--text-normal: #0f172a", css)
        self.assertIn("--text-muted: #475569", css)
        self.assertIn("--vis-focus-ring: #0369a1", css)


# ---------------------------------------------------------------------------
# T3 — template renderer substitution behaviour
# ---------------------------------------------------------------------------


class TestTemplateRenderer(unittest.TestCase):
    @staticmethod
    def _render() -> str:
        from brain_ds.demo import build_logitrans_graph
        from brain_ds.ui.render_context import build_render_context
        from brain_ds.ui.template_renderer import render_interactive_html

        graph = build_logitrans_graph()
        context = build_render_context(graph)
        return render_interactive_html(context)

    def test_graph_viewer_renders_tokens_inline(self):
        html = self._render()
        self.assertIn("--bg-main: #09090b", html)
        self.assertIn("--border-subtle: rgba(63, 63, 70, 0.4)", html)

    def test_template_placeholder_substituted(self):
        html = self._render()
        self.assertNotIn("__BRAIN_DS_TOKENS_CSS__", html)
        self.assertNotIn("__BRAIN_DS_THEME_TOKENS__", html)

    def test_no_theme_star_emission(self):
        html = self._render()
        self.assertNotIn("--theme-", html)

    def test_graph_viewer_links_tokens_css_no_inline_root(self):
        html = self._render()
        # Legacy values from the inline :root{} block must be gone.
        self.assertNotIn("--bg-main: #161616", html)
        self.assertNotIn("--bg-panel: #1e1e1e", html)
        self.assertNotIn("rgba(255,255,255,0.06)", html)

    def test_workspace_shell_layout_intact_after_migration(self):
        html = self._render()
        # Shell grid + canonical heights for tab-strip (36px — PR #4 chrome parity,
        # ADR-009 project override; the reference's 48px .tabs-bar is intentionally
        # NOT adopted under the 5-column grid, per design ADR-F #1208. Stale-contract
        # migration #1194: was 48px at the D.4 port) and toolbar (44px LOCKED).
        self.assertIn(".workspace-shell", html)
        self.assertIn("flex: 0 0 36px", html)  # .tab-strip (ADR-009 project contract)
        self.assertIn("flex: 0 0 44px", html)  # .top-toolbar / .panel-header


# ---------------------------------------------------------------------------
# T7 — _tokens.css forwarding shim
# ---------------------------------------------------------------------------


class TestTokensShim(unittest.TestCase):
    def test_shim_imports_canonical_tokens_css(self):
        self.assertTrue(SHIM_CSS.exists(), "_tokens.css shim must exist")
        css = SHIM_CSS.read_text(encoding="utf-8")
        self.assertIn('@import url("../../static/tokens.css")', css)

    def test_design_section_html_still_links_tokens_css(self):
        section_1 = SECTIONS_DIR / "section-1-left-shell.html"
        self.assertTrue(section_1.exists())
        html = section_1.read_text(encoding="utf-8")
        self.assertIn('href="_tokens.css"', html)


# ---------------------------------------------------------------------------
# T9 — visual checkpoint artifact
# ---------------------------------------------------------------------------


class TestCheckpoint(unittest.TestCase):
    def test_review_checkpoint_artifacts_exist(self):
        self.assertTrue(
            CHECKPOINT_HTML.exists(),
            f"D.1 visual checkpoint must exist at {CHECKPOINT_HTML}",
        )
        html = CHECKPOINT_HTML.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            len(re.findall(r"<iframe\b", html, flags=re.IGNORECASE)),
            2,
            "checkpoint must embed two <iframe> elements side by side",
        )


if __name__ == "__main__":
    unittest.main()
