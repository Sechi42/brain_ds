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

THEME_TOKENS = {
    "dark": {
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
        # Slice 7 contrast targets
        "score_badge_bg": "#fbbf24",
        "score_badge_text": "#0f172a",
        "popover_bg": "#1e293b",
        "popover_text": "#e2e8f0",
        "edge_default": "#94a3b8",
        "edge_highlight": "#cbd5e1",
        "halo": "#38bdf8",
    },
    "light": {
        "background": "#f8fafc",
        "surface": "#ffffff",
        "surface_elevated": "#ffffff",
        "border": "#cbd5e1",
        "text": "#0f172a",
        "text_muted": "#475569",
        "focus_ring": "#0369a1",
        "card_bg": "#ffffff",
        "card_shadow": "0 6px 18px rgba(15, 23, 40, 0.10)",
        "card_accent_border": "#0369a1",
        "card_divider": "#cbd5e1",
        "card_radius": "8px",
        "spacing_sm": "0.5rem",
        "spacing_md": "0.75rem",
        "spacing_lg": "1rem",
        "target_min": "44px",
        # Slice 7 contrast targets
        "score_badge_bg": "#fbbf24",
        "score_badge_text": "#0f172a",
        "popover_bg": "#ffffff",
        "popover_text": "#0f172a",
        "edge_default": "#475569",
        "edge_highlight": "#1e293b",
        "halo": "#0369a1",
    },
}

# Backward-compatible alias for legacy imports/consumers.
HTML_TOKENS = THEME_TOKENS["dark"]

ENTITY_TYPE_COLORS = {
    "dark": dict(TYPE_COLORS),
    "light": {
        "Organization": "#1f2937",
        "Department": "#1d4ed8",
        "Role": "#166534",
        "Data Source": "#6d28d9",
        "Heuristic": "#b45309",
        "Tacit Knowledge": "#0e7490",
        "Problem / Improvement Area": "#b91c1c",
        "Project": "#4338ca",
        "Risk": "#991b1b",
        "Decision": "#0f766e",
        "KPI": "#92400e",
        "Solution": "#047857",
        "Unknown": "#475569",
    },
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
    dark_tokens = THEME_TOKENS["dark"]
    light_tokens = THEME_TOKENS["light"]

    lines = [":root {"]
    for key, value in dark_tokens.items():
        lines.append(f"  --theme-{key}: {value};")
    lines.append("}")

    lines.append('[data-theme="light"] {')
    for key, value in light_tokens.items():
        lines.append(f"  --theme-{key}: {value};")
    lines.append("}")

    return "\n".join(lines)


def vis_options_json() -> str:
    return json.dumps(VIS_OPTIONS)


def color_for_type(entity_type_value: str, theme: str = "dark") -> str:
    palette = ENTITY_TYPE_COLORS.get(theme, ENTITY_TYPE_COLORS["dark"])
    return palette.get(entity_type_value, palette.get(EntityType.UNKNOWN.value, EntityType.UNKNOWN.color))
