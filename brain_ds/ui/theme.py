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
        # Slice 2 token system v2
        "space_0": "0",
        "space_1": "0.25rem",
        "space_2": "0.5rem",
        "space_3": "0.75rem",
        "space_4": "1rem",
        "space_5": "1.5rem",
        "space_6": "2rem",
        "space_8": "3rem",
        "font_xs": "0.75rem",
        "font_sm": "0.875rem",
        "font_md": "1rem",
        "font_lg": "1.125rem",
        "font_xl": "1.25rem",
        "font_2xl": "1.5rem",
        "font_weight_regular": "400",
        "font_weight_medium": "500",
        "font_weight_semibold": "600",
        "line_height_tight": "1.25",
        "line_height_normal": "1.5",
        "line_height_relaxed": "1.65",
        "font_family_sans": '-apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", system-ui, "Inter", Roboto, "Helvetica Neue", Arial, sans-serif',
        "font_family_mono": 'ui-monospace, "Cascadia Code", "Fira Code", Consolas, monospace',
        "state_hover_bg": "#1e293b",
        "state_hover_fg": "#f1f5f9",
        "state_selected_bg": "#0c4a6e",
        "state_selected_fg": "#e0f2fe",
        "state_focus_ring": FOCUS_RING_COLOR,
        "state_disabled_bg": "#1f2937",
        "state_disabled_fg": "#94a3b8",
        "state_danger_bg": "#7f1d1d",
        "state_danger_fg": "#fee2e2",
        # Danger chrome token mirror (canonical CSS source: tokens.css --danger).
        # DATA for contrast tooling only — NOT a CSS emitter.
        "danger": "#f87171",
        "danger_soft": "rgba(239, 68, 68, 0.1)",
        "status_active": "#059669",
        "status_warn": "#d97706",
        "status_danger": "#f87171",
        "state_success_bg": "#14532d",
        "state_success_fg": "#dcfce7",
        "state_info_bg": "#0c4a6e",
        "state_info_fg": "#e0f2fe",
        "state_warning_bg": "#78350f",
        "state_warning_fg": "#fef3c7",
        "surface_canvas": BACKGROUND_COLOR,
        "surface_panel": SURFACE_COLOR,
        "surface_overlay": "rgba(2, 6, 23, 0.62)",
        "edge_dash": "6",
        "edge_arrowhead_size": "8",
        "entity_organization_fill": "#111827",
        "entity_department_fill": "#2563eb",
        "entity_role_fill": "#16a34a",
        "entity_data_source_fill": "#7c3aed",
        "entity_heuristic_fill": "#f59e0b",
        "entity_tacit_knowledge_fill": "#0ea5e9",
        "entity_problem_improvement_area_fill": "#dc2626",
        "entity_project_fill": "#4f46e5",
        "entity_risk_fill": "#b91c1c",
        "entity_decision_fill": "#0f766e",
        "entity_kpi_fill": "#a16207",
        "entity_solution_fill": "#059669",
        "entity_unknown_fill": "#6b7280",
        "border_subtle": BORDER_COLOR,
        "border_default": "#475569",
        "border_strong": "#64748b",
        "border_emphasis": FOCUS_RING_COLOR,
        "shadow_xs": "0 1px 2px rgba(2, 6, 23, 0.40)",
        "shadow_sm": "0 6px 18px rgba(15, 23, 40, 0.35)",
        "shadow_md": "0 12px 28px rgba(15, 23, 40, 0.45)",
        "shadow_lg": "0 20px 40px rgba(15, 23, 40, 0.50)",
        "shadow_overlay": "0 24px 64px rgba(2, 6, 23, 0.55)",
        "radius_sm": "4px",
        "radius_md": "8px",
        "radius_lg": "12px",
        "radius_pill": "9999px",
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
        # Slice 2 token system v2
        "space_0": "0",
        "space_1": "0.25rem",
        "space_2": "0.5rem",
        "space_3": "0.75rem",
        "space_4": "1rem",
        "space_5": "1.5rem",
        "space_6": "2rem",
        "space_8": "3rem",
        "font_xs": "0.75rem",
        "font_sm": "0.875rem",
        "font_md": "1rem",
        "font_lg": "1.125rem",
        "font_xl": "1.25rem",
        "font_2xl": "1.5rem",
        "font_weight_regular": "400",
        "font_weight_medium": "500",
        "font_weight_semibold": "600",
        "line_height_tight": "1.25",
        "line_height_normal": "1.5",
        "line_height_relaxed": "1.65",
        "font_family_sans": '-apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", system-ui, "Inter", Roboto, "Helvetica Neue", Arial, sans-serif',
        "font_family_mono": 'ui-monospace, "Cascadia Code", "Fira Code", Consolas, monospace',
        "state_hover_bg": "#e2e8f0",
        "state_hover_fg": "#0f172a",
        "state_selected_bg": "#bfdbfe",
        "state_selected_fg": "#0c4a6e",
        "state_focus_ring": "#0369a1",
        "state_disabled_bg": "#e2e8f0",
        "state_disabled_fg": "#64748b",
        "state_danger_bg": "#fee2e2",
        "state_danger_fg": "#7f1d1d",
        # Danger chrome token mirror (canonical CSS source: tokens.css --danger).
        "danger": "#dc2626",
        "danger_soft": "rgba(220, 38, 38, 0.1)",
        "status_active": "#047857",
        "status_warn": "#b45309",
        "status_danger": "#dc2626",
        "state_success_bg": "#dcfce7",
        "state_success_fg": "#14532d",
        "state_info_bg": "#dbeafe",
        "state_info_fg": "#1e3a8a",
        "state_warning_bg": "#fef3c7",
        "state_warning_fg": "#78350f",
        "surface_canvas": "#f8fafc",
        "surface_panel": "#ffffff",
        "surface_overlay": "rgba(15, 23, 42, 0.28)",
        "edge_dash": "6",
        "edge_arrowhead_size": "8",
        "entity_organization_fill": "#1f2937",
        "entity_department_fill": "#1d4ed8",
        "entity_role_fill": "#166534",
        "entity_data_source_fill": "#6d28d9",
        "entity_heuristic_fill": "#b45309",
        "entity_tacit_knowledge_fill": "#0e7490",
        "entity_problem_improvement_area_fill": "#b91c1c",
        "entity_project_fill": "#4338ca",
        "entity_risk_fill": "#991b1b",
        "entity_decision_fill": "#0f766e",
        "entity_kpi_fill": "#92400e",
        "entity_solution_fill": "#047857",
        "entity_unknown_fill": "#475569",
        "border_subtle": "#e2e8f0",
        "border_default": "#cbd5e1",
        "border_strong": "#94a3b8",
        "border_emphasis": "#0369a1",
        "shadow_xs": "0 1px 2px rgba(15, 23, 42, 0.06)",
        "shadow_sm": "0 6px 18px rgba(15, 23, 42, 0.10)",
        "shadow_md": "0 12px 28px rgba(15, 23, 42, 0.14)",
        "shadow_lg": "0 20px 40px rgba(15, 23, 42, 0.18)",
        "shadow_overlay": "0 24px 64px rgba(15, 23, 42, 0.22)",
        "radius_sm": "4px",
        "radius_md": "8px",
        "radius_lg": "12px",
        "radius_pill": "9999px",
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


# NOTE (Phase D.1, modern-design-tokens): the previous `theme_tokens_css()`
# function emitted `--theme-*` CSS variables that no CSS file ever consumed.
# All runtime CSS tokens (palette, borders, radius, font weights, motion) now
# live in brain_ds/ui/static/tokens.css and are inlined at render time via
# template_renderer.py. THEME_TOKENS above is preserved as DATA for contrast
# tooling (contrast-audit.json) and the test suite — it is no longer used to
# generate CSS. Do not reintroduce a CSS emitter here; extend tokens.css
# instead.


def vis_options_json() -> str:
    return json.dumps(VIS_OPTIONS)


def color_for_type(entity_type_value: str, theme: str = "dark") -> str:
    palette = ENTITY_TYPE_COLORS.get(theme, ENTITY_TYPE_COLORS["dark"])
    return palette.get(entity_type_value, palette.get(EntityType.UNKNOWN.value, EntityType.UNKNOWN.color))
