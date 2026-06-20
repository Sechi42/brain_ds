from __future__ import annotations

import importlib.resources as resources
import json
from pathlib import Path

from brain_ds.ui.icons import build_sprite

ASSETS_DIR = Path(__file__).with_name("assets")
TEMPLATES_DIR = Path(__file__).with_name("templates")
STATIC_DIR = Path(__file__).with_name("static")


def render_vault_picker_html(
    graphs: list[dict],
    *,
    permissions: dict[str, dict[str, bool]] | None = None,
    active_graph_id: str | None = None,
) -> str:
    """Render the vault-picker page with org rows and create-org form.

    Args:
        graphs: list of {"id": str, "label": str} dicts (from _graphs_payload).

    Returns:
        Fully rendered HTML string with tokens substituted and org rows injected.
    """
    templates_root = resources.files("brain_ds.ui").joinpath("templates")
    static_root = resources.files("brain_ds.ui").joinpath("static")

    template = templates_root.joinpath("vault_picker.html").read_text(encoding="utf-8")
    tokens_css = static_root.joinpath("tokens.css").read_text(encoding="utf-8")

    # Build server-rendered workspace rows (R1.1–R1.7, S1-A, S1-B, S1-C).
    # Structure per card:
    #   - Primary CTA: <a data-workspace-open> to open the workspace
    #   - <h2 class="workspace-name"> as prominent heading
    #   - <details class="workspace-manage"> collapsed at rest, containing:
    #       - "Remove from list" button (secondary, NOT primary-styled)
    #       - <details class="workspace-danger-zone"> for hard delete
    rows: list[str] = []
    for index, g in enumerate(graphs, start=1):
        graph_id = _escape_html(str(g["id"]))
        workspace_name = _escape_html(str(g["label"]))
        raw_graph_id = str(g["id"])
        can_delete = True if permissions is None else bool(permissions.get(raw_graph_id, {}).get("workspace_admin"))
        is_active = raw_graph_id == active_graph_id
        confirm_id = f"workspace-delete-confirm-{index}"
        active_ack_id = f"workspace-active-ack-{index}"
        manage_html = ""
        if can_delete:
            manage_html = (
                # Collapsed manage block — secondary/destructive actions
                '<details class="workspace-manage">'
                '<summary class="workspace-manage-summary">Manage</summary>'
                '<div class="workspace-manage-body">'
                # Remove from list — secondary, NOT primary-styled
                f'<button type="button" class="workspace-action-btn workspace-action-btn--secondary" '
                f'data-workspace-remove '
                f'data-workspace-path="{graph_id}" '
                f'data-active-graph-id="{_escape_html(str(active_graph_id or ""))}" '
                f'data-active-workspace="{str(is_active).lower()}" '
                f'data-graph-id="{graph_id}">Eliminar · Remove from list</button>'
                # Nested danger zone for hard delete
                '<details class="workspace-danger-zone">'
                '<summary class="workspace-action-btn workspace-action-btn--danger">Delete all data</summary>'
                f'<form class="workspace-danger-form" '
                f'data-workspace-path="{graph_id}" '
                f'data-active-graph-id="{_escape_html(str(active_graph_id or ""))}" '
                f'data-active-workspace="{str(is_active).lower()}" '
                f'data-graph-id="{graph_id}" '
                f'data-workspace-name="{workspace_name}">'
                '<p class="workspace-danger-copy">Irreversible. Type the workspace name or path to confirm.</p>'
                f'<label for="{confirm_id}" class="visually-hidden">Type {workspace_name} or path to confirm</label>'
                f'<input id="{confirm_id}" class="workspace-confirm-input" name="typed_confirm" type="text" '
                f'placeholder="Type {workspace_name} or path" autocomplete="off" required />'
                f'<label for="{active_ack_id}" class="workspace-active-ack">'
                f'<input id="{active_ack_id}" name="active_acknowledged" type="checkbox" '
                f'{"required" if is_active else ""} />'
                'I understand this is the active workspace.'
                '</label>'
                '<button type="submit" class="workspace-action-btn workspace-action-btn--danger" disabled>'
                'Delete all data</button>'
                '<p class="workspace-action-status" role="status" aria-live="polite"></p>'
                '</form></details>'
                '</div></details>'
            )
        rows.append(
            f'      <li class="workspace-card" '
            f'data-graph-id="{graph_id}" '
            f'data-workspace-path="{graph_id}" '
            f'data-workspace-name="{workspace_name}">'
            # Prominent heading
            f'<h2 class="workspace-name" data-workspace-name="{workspace_name}">{workspace_name}</h2>'
            # Primary open CTA
            f'<a class="org-row workspace-open-cta" '
            f'href="/?graph_id={graph_id}" '
            f'data-workspace-open '
            f'data-graph-id="{graph_id}">Open workspace</a>'
            f'{manage_html}</li>'
        )
    rows_html = "\n".join(rows)

    return (
        template
        .replace("__BRAIN_DS_TOKENS_CSS__", tokens_css)
        .replace("__BRAIN_DS_ORG_ROWS__", rows_html)
    )


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for org labels injected into the template."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_interactive_html(context: dict, *, template_path: Path | None = None) -> str:
    if template_path:
        template = template_path.read_text(encoding="utf-8")
        vis_css = ASSETS_DIR.joinpath("viewer.bundle.css").read_text(encoding="utf-8")
        vis_js = ASSETS_DIR.joinpath("viewer.bundle.js").read_text(encoding="utf-8")
        sprite_path = ASSETS_DIR.joinpath("icons.sprite.svg")
        if not sprite_path.exists():
            build_sprite(ASSETS_DIR.joinpath("icons"), sprite_path)
        icon_sprite = sprite_path.read_text(encoding="utf-8")
        tokens_css = STATIC_DIR.joinpath("tokens.css").read_text(encoding="utf-8")
    else:
        templates_root = resources.files("brain_ds.ui").joinpath("templates")
        assets_root = resources.files("brain_ds.ui").joinpath("assets")
        static_root = resources.files("brain_ds.ui").joinpath("static")
        template = templates_root.joinpath("graph_viewer.html").read_text(encoding="utf-8")
        vis_css = assets_root.joinpath("viewer.bundle.css").read_text(encoding="utf-8")
        vis_js = assets_root.joinpath("viewer.bundle.js").read_text(encoding="utf-8")
        icon_sprite = assets_root.joinpath("icons.sprite.svg").read_text(encoding="utf-8")
        tokens_css = static_root.joinpath("tokens.css").read_text(encoding="utf-8")

    meta = dict(context.get("meta") or {})
    if "graph_id" not in meta and context.get("graph_id") is not None:
        meta["graph_id"] = context.get("graph_id")
    status_label = str(meta.get("status_label") or "LIVE").upper()[:4]
    meta["status_label"] = status_label or "LIVE"
    context_with_defaults = dict(context)
    context_with_defaults["meta"] = meta

    context_json = json.dumps(context_with_defaults, ensure_ascii=False)
    return (
        template.replace("__BRAIN_DS_TOKENS_CSS__", tokens_css)
        .replace("__BRAIN_DS_RENDER_CONTEXT__", context_json)
        .replace("__VIS_NETWORK_CSS__", vis_css)
        .replace("__VIS_NETWORK_JS__", vis_js)
        .replace("__BRAIN_DS_ICON_SPRITE__", icon_sprite)
    )
