import unittest
import json
from pathlib import Path

from brain_ds.ontology import Graph
from brain_ds.ui.render_context import build_render_context
from brain_ds.ui.theme import ENTITY_TYPE_COLORS, THEME_TOKENS


CONTRAST_AUDIT_PATH = Path("brain_ds/ui/contrast-audit.json")


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


def contrast_ratio(color_a: str, color_b: str) -> float:
    l1 = _luminance(color_a)
    l2 = _luminance(color_b)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class TestThemePalettes(unittest.TestCase):
    def test_theme_has_dark_and_light_tokens(self):
        self.assertIn("dark", THEME_TOKENS)
        self.assertIn("light", THEME_TOKENS)

    def test_wcag_text_and_ui_pairs_pass_in_both_themes(self):
        for theme_name, tokens in THEME_TOKENS.items():
            # Body text AA (>= 4.5)
            self.assertGreaterEqual(
                contrast_ratio(tokens["text"], tokens["background"]),
                4.5,
                f"{theme_name} body text contrast must be >= 4.5",
            )
            # Muted text AA (>= 4.5)
            self.assertGreaterEqual(
                contrast_ratio(tokens["text_muted"], tokens["background"]),
                4.5,
                f"{theme_name} muted text contrast must be >= 4.5",
            )
            # Focus ring non-text UI contrast (>= 3)
            self.assertGreaterEqual(
                contrast_ratio(tokens["focus_ring"], tokens["background"]),
                3.0,
                f"{theme_name} focus ring contrast must be >= 3",
            )
            # Score badge contrast in both themes (REQ-7.4)
            self.assertGreaterEqual(
                contrast_ratio(tokens["score_badge_text"], tokens["score_badge_bg"]),
                3.0,
                f"{theme_name} score badge contrast must be >= 3",
            )
            # Popover contrast in both themes (REQ-7.4)
            self.assertGreaterEqual(
                contrast_ratio(tokens["popover_text"], tokens["popover_bg"]),
                4.5,
                f"{theme_name} popover text contrast must be >= 4.5",
            )

    def test_entity_type_light_variants_are_distinct_for_low_contrast_dark_colors(self):
        self.assertNotEqual(
            ENTITY_TYPE_COLORS["dark"]["Organization"],
            ENTITY_TYPE_COLORS["light"]["Organization"],
        )

    def test_slice2_token_categories_exist_in_both_themes(self):
        required_keys = {
            "space_0",
            "space_1",
            "space_2",
            "space_3",
            "space_4",
            "space_5",
            "space_6",
            "space_8",
            "font_xs",
            "font_sm",
            "font_md",
            "font_lg",
            "font_xl",
            "font_2xl",
            "font_weight_regular",
            "font_weight_medium",
            "font_weight_semibold",
            "line_height_tight",
            "line_height_normal",
            "line_height_relaxed",
            "font_family_sans",
            "font_family_mono",
            "state_hover_bg",
            "state_hover_fg",
            "state_selected_bg",
            "state_selected_fg",
            "state_focus_ring",
            "state_disabled_bg",
            "state_disabled_fg",
            "state_danger_bg",
            "state_danger_fg",
            "state_success_bg",
            "state_success_fg",
            "state_info_bg",
            "state_info_fg",
            "state_warning_bg",
            "state_warning_fg",
            "surface_canvas",
            "surface_panel",
            "surface_elevated",
            "surface_overlay",
            "border_subtle",
            "border_default",
            "border_strong",
            "border_emphasis",
            "shadow_xs",
            "shadow_sm",
            "shadow_md",
            "shadow_lg",
            "shadow_overlay",
            "radius_sm",
            "radius_md",
            "radius_lg",
            "radius_pill",
        }
        for theme_name, tokens in THEME_TOKENS.items():
            missing = sorted(required_keys - set(tokens.keys()))
            self.assertEqual([], missing, f"{theme_name} missing Slice 2 tokens: {missing}")

    def test_spacing_and_radius_aliases_remain_available(self):
        for _theme_name, tokens in THEME_TOKENS.items():
            self.assertEqual("0.5rem", tokens["spacing_sm"])
            self.assertEqual("0.75rem", tokens["spacing_md"])
            self.assertEqual("1rem", tokens["spacing_lg"])
            self.assertEqual(tokens["radius_md"], tokens["card_radius"])

    def test_motion_tokens_and_reduced_motion_block_present(self):
        # Phase D.1: motion tokens migrated from theme_tokens_css() into
        # brain_ds/ui/static/tokens.css. Assert they live there now.
        tokens_path = Path("brain_ds/ui/static/tokens.css")
        self.assertTrue(tokens_path.exists(), "canonical tokens.css must exist")
        css = tokens_path.read_text(encoding="utf-8")
        self.assertIn("--duration-fast: 120ms;", css)
        self.assertIn("--duration-normal: 200ms;", css)
        self.assertIn("--duration-slow: 320ms;", css)
        self.assertIn("--ease-standard: cubic-bezier(0.2, 0, 0, 1);", css)
        self.assertIn("--ease-emphasized: cubic-bezier(0.3, 0, 0, 1);", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("--duration-fast: 0ms;", css)
        self.assertIn("--duration-normal: 0ms;", css)
        self.assertIn("--duration-slow: 0ms;", css)

    def test_theme_tokens_css_function_removed(self):
        # Sentinel: prevents reintroduction. tokens.css is the single source of
        # CSS-emitted tokens; theme.py keeps only THEME_TOKENS (data) +
        # ENTITY_TYPE_COLORS + color_for_type + vis_options_json.
        import brain_ds.ui.theme as theme_module

        self.assertFalse(
            hasattr(theme_module, "theme_tokens_css"),
            "theme_tokens_css() must be retired; tokens.css is the source of truth",
        )

    def test_contrast_audit_has_26_entries_and_no_fail_status(self):
        self.assertTrue(CONTRAST_AUDIT_PATH.exists(), "contrast-audit.json must exist")
        payload = json.loads(CONTRAST_AUDIT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(26, len(payload), "audit must contain 13 entity fills x 2 themes")

        allowed_status = {"pass", "fail", "outline-fallback"}
        fails = []
        for item in payload:
            self.assertIn("entity_type", item)
            self.assertIn("theme", item)
            self.assertIn(item["theme"], {"dark", "light"})
            self.assertIn("fill_hex", item)
            self.assertIn("surface_hex", item)
            self.assertIn("ratio", item)
            self.assertIn("status", item)
            self.assertIn(item["status"], allowed_status)
            if item["status"] == "fail":
                fails.append(item)
        self.assertEqual([], fails, f"contrast audit contains failing entries: {fails}")


class TestRenderContextThemeColors(unittest.TestCase):
    def test_render_context_emits_node_color_variants(self):
        payload = {
            "org": "ThemeOrg",
            "nodes": [{"id": "org-1", "label": "Org", "type": "Organization"}],
            "edges": [],
        }
        context = build_render_context(Graph.from_v1(payload))
        color = context["nodes"][0]["color"]
        self.assertIsInstance(color, dict)
        self.assertIn("background", color)
        self.assertIn("dark", color)
        self.assertIn("light", color)
        self.assertTrue(color["dark"].startswith("#"))
        self.assertTrue(color["light"].startswith("#"))


if __name__ == "__main__":
    unittest.main()
