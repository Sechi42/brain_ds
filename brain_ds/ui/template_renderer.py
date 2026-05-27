from __future__ import annotations

import importlib.resources as resources
import json
from pathlib import Path

from brain_ds.ui.icons import build_sprite

ASSETS_DIR = Path(__file__).with_name("assets")
TEMPLATES_DIR = Path(__file__).with_name("templates")
STATIC_DIR = Path(__file__).with_name("static")


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
