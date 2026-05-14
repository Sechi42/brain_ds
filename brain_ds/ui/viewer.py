from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from brain_ds.ontology import Graph

from .render_context import build_render_context
from .simple_renderer import render_simple_html
from .template_renderer import render_interactive_html


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "org"


def load_graph(json_path: Path) -> Graph:
    with json_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return Graph.from_v1(payload)


def derive_output_path(json_path: Path, graph: Graph) -> Path:
    return json_path.with_name(f"{slugify(str(graph.org or 'org'))}-graph.html")


def render_graph_file(
    json_path: Path,
    *,
    output_path: Path | None = None,
    open_browser: bool = False,
    simple: bool = False,
    network_cls: type | None = None,
) -> Path:
    graph = load_graph(json_path)
    final_output = output_path or derive_output_path(json_path, graph)
    final_output.parent.mkdir(parents=True, exist_ok=True)

    if simple:
        return render_simple_html(
            graph,
            output_path=final_output,
            open_browser=open_browser,
            network_cls=network_cls,
        )

    context = build_render_context(graph)
    html = render_interactive_html(context)
    final_output.write_text(html, encoding="utf-8")

    if open_browser:
        try:
            import webbrowser

            opened = webbrowser.open(final_output.as_uri())
            if not opened:
                print(f"HTML viewer generated: {final_output}")
        except Exception:
            print(f"HTML viewer generated: {final_output}")

    return final_output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="generate_viewer.py")
    parser.add_argument("graph_json", help="Path to graph JSON")
    parser.add_argument("--output", help="Output HTML path (optional)")
    parser.add_argument("--open", action="store_true", dest="open_browser", help="Open HTML after generation")
    parser.add_argument("--simple", action="store_true", help="Use legacy PyVis renderer")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    json_path = Path(args.graph_json).resolve()

    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        return 2

    output = Path(args.output).resolve() if args.output else None
    try:
        output_path = render_graph_file(
            json_path,
            output_path=output,
            open_browser=args.open_browser,
            simple=args.simple,
        )
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON - {exc}", file=sys.stderr)
        return 2
    except RuntimeError:
        print("Error: pyvis not installed. Run: uv sync --extra simple", file=sys.stderr)
        return 1

    print(f"HTML viewer generated: {output_path}")
    print(f"Graph JSON used: {json_path}")
    return 0
