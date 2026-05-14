from __future__ import annotations

import json

from brain_ds.ontology import EntityType, TYPE_COLORS

BACKGROUND_COLOR = "#0f1728"
FONT_COLOR = "#e2e8f0"
SURFACE_COLOR = "#132037"
SURFACE_ELEVATED_COLOR = "#1e293b"
BORDER_COLOR = "#334155"
TEXT_MUTED_COLOR = "#cbd5e1"
FOCUS_RING_COLOR = "#38bdf8"

HTML_TOKENS = {
    "background": BACKGROUND_COLOR,
    "surface": SURFACE_COLOR,
    "surface_elevated": SURFACE_ELEVATED_COLOR,
    "border": BORDER_COLOR,
    "text": FONT_COLOR,
    "text_muted": TEXT_MUTED_COLOR,
    "focus_ring": FOCUS_RING_COLOR,
    "card_bg": SURFACE_ELEVATED_COLOR,
    "card_shadow": "0 6px 18px rgba(15, 23, 40, 0.35)",
    "card_accent_border": FOCUS_RING_COLOR,
    "card_divider": BORDER_COLOR,
    "card_radius": "8px",
    "spacing_sm": "0.5rem",
    "spacing_md": "0.75rem",
    "spacing_lg": "1rem",
    "target_min": "44px",
}

VIS_OPTIONS = {
    "layout": {
        "hierarchical": {
            "enabled": True,
            "direction": "UD",
            "sortMethod": "hubsize",
            "nodeSpacing": 190,
            "treeSpacing": 260,
        }
    },
    "interaction": {
        "hover": True,
        "navigationButtons": True,
        "keyboard": True,
        "tooltipDelay": 120,
    },
    "physics": {"enabled": False},
    "edges": {
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}},
        "smooth": {"enabled": True, "type": "cubicBezier"},
        "font": {"size": 11, "align": "middle", "color": FONT_COLOR},
        "color": {"color": "#94a3b8", "highlight": "#cbd5e1"},
    },
    "nodes": {
        "shape": "dot",
        "size": 18,
        "font": {"size": 13, "color": FONT_COLOR},
        "borderWidth": 1,
    },
}


def theme_tokens_css() -> str:
    lines = [":root {"]
    for key, value in HTML_TOKENS.items():
        lines.append(f"  --theme-{key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def vis_options_json() -> str:
    return json.dumps(VIS_OPTIONS)


def color_for_type(entity_type_value: str) -> str:
    return TYPE_COLORS.get(entity_type_value, EntityType.UNKNOWN.color)
