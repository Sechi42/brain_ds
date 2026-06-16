from __future__ import annotations

import importlib.resources as resources
import json
from pathlib import Path

from brain_ds.ui.icons import build_sprite

ASSETS_DIR = Path(__file__).with_name("assets")
TEMPLATES_DIR = Path(__file__).with_name("templates")
STATIC_DIR = Path(__file__).with_name("static")


def render_vault_picker_html(graphs: list[dict]) -> str:
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

    # Build server-rendered workspace rows (R8 + B safe-confirm actions).
    rows: list[str] = []
    for index, g in enumerate(graphs, start=1):
        workspace_path = _escape_html(str(g["id"]))
        workspace_name = _escape_html(str(g["label"]))
        confirm_id = f"workspace-delete-confirm-{index}"
        rows.append(
            "      <li class=\"workspace-card\" "
            f'data-workspace-path="{workspace_path}" data-workspace-name="{workspace_name}">'
            f'<a class="org-row" href="/?graph_id={workspace_path}">{workspace_name}</a>'
            "<div class=\"workspace-actions\">"
            f'<button type="button" class="workspace-action-btn workspace-action-btn--primary" '
            f'data-workspace-remove data-workspace-path="{workspace_path}">Remove from list</button>'
            "<details class=\"workspace-danger-zone\">"
            "<summary class=\"workspace-action-btn workspace-action-btn--danger\">Delete all data</summary>"
            f'<form class="workspace-danger-form" data-workspace-path="{workspace_path}" data-workspace-name="{workspace_name}">'
            "<p class=\"workspace-danger-copy\">Irreversible. Type the workspace name or path to confirm.</p>"
            f'<label for="{confirm_id}" class="visually-hidden">Type {workspace_name} or path to confirm</label>'
            f'<input id="{confirm_id}" class="workspace-confirm-input" name="typed_confirm" type="text" '
            f'placeholder="Type {workspace_name} or path" autocomplete="off" required />'
            '<button type="submit" class="workspace-action-btn workspace-action-btn--danger" disabled>'
            "Delete all data</button>"
            '<p class="workspace-action-status" role="status" aria-live="polite"></p>'
            "</form></details></div></li>"
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
