from __future__ import annotations

import importlib.resources as resources
import json
from pathlib import Path

from brain_ds.ui.icons import build_sprite
from brain_ds.ui.theme import theme_tokens_css

ASSETS_DIR = Path(__file__).with_name("assets")
TEMPLATES_DIR = Path(__file__).with_name("templates")


def render_interactive_html(context: dict, *, template_path: Path | None = None) -> str:
    if template_path:
        template = template_path.read_text(encoding="utf-8")
        vis_css = ASSETS_DIR.joinpath("viewer.bundle.css").read_text(encoding="utf-8")
        vis_js = ASSETS_DIR.joinpath("viewer.bundle.js").read_text(encoding="utf-8")
        sprite_path = ASSETS_DIR.joinpath("icons.sprite.svg")
        if not sprite_path.exists():
            build_sprite(ASSETS_DIR.joinpath("icons"), sprite_path)
        icon_sprite = sprite_path.read_text(encoding="utf-8")
    else:
        templates_root = resources.files("brain_ds.ui").joinpath("templates")
        assets_root = resources.files("brain_ds.ui").joinpath("assets")
        template = templates_root.joinpath("graph_viewer.html").read_text(encoding="utf-8")
        vis_css = assets_root.joinpath("viewer.bundle.css").read_text(encoding="utf-8")
        vis_js = assets_root.joinpath("viewer.bundle.js").read_text(encoding="utf-8")
        icon_sprite = assets_root.joinpath("icons.sprite.svg").read_text(encoding="utf-8")

    context_json = json.dumps(context, ensure_ascii=False)
    return (
        template.replace("__BRAIN_DS_THEME_TOKENS__", theme_tokens_css())
        .replace("__BRAIN_DS_RENDER_CONTEXT__", context_json)
        .replace("__VIS_NETWORK_CSS__", vis_css)
        .replace("__VIS_NETWORK_JS__", vis_js)
        .replace("__BRAIN_DS_ICON_SPRITE__", icon_sprite)
    )
