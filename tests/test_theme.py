import unittest

from brain_ds.ontology import Graph
from brain_ds.ui.render_context import build_render_context
from brain_ds.ui.theme import ENTITY_TYPE_COLORS, THEME_TOKENS


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
