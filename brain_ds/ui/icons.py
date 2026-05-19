from __future__ import annotations

from pathlib import Path
import re


ICON_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _symbol_name(path: Path) -> str:
    name = path.stem
    if not ICON_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid icon filename '{path.name}'. Use kebab-case.")
    return f"icon-{name}"


def _extract_inner_svg(svg_text: str) -> tuple[str, str]:
    viewbox_match = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_text)
    if not viewbox_match:
        raise ValueError("SVG must include viewBox")
    viewbox = viewbox_match.group(1)
    body_match = re.search(r"<svg[^>]*>([\s\S]*?)</svg>", svg_text, flags=re.IGNORECASE)
    if not body_match:
        raise ValueError("SVG must have a root <svg>...</svg>")
    inner = body_match.group(1).strip()
    return viewbox, inner


def sprite_string(src_dir: Path) -> str:
    icons = sorted(src_dir.glob("*.svg"))
    symbols: list[str] = []
    for icon in icons:
        symbol_id = _symbol_name(icon)
        viewbox, inner = _extract_inner_svg(icon.read_text(encoding="utf-8"))
        symbols.append(f'<symbol id="{symbol_id}" viewBox="{viewbox}">{inner}</symbol>')
    symbols_markup = "\n      ".join(symbols)
    return (
        '<svg style="display:none" aria-hidden="true">\n'
        "  <defs>\n"
        f"      {symbols_markup}\n"
        "  </defs>\n"
        "</svg>"
    )


def build_sprite(src_dir: Path, out_path: Path) -> int:
    sprite = sprite_string(src_dir)
    out_path.write_text(sprite, encoding="utf-8")
    return len(sprite.encode("utf-8"))
