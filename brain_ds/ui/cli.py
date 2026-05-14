from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .viewer import render_graph_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain_ds")
    subparsers = parser.add_subparsers(dest="command")

    ui_parser = subparsers.add_parser("ui", help="Render graph JSON as interactive HTML")
    ui_parser.add_argument("graph_json", help="Path to graph JSON")
    ui_parser.add_argument("--output", help="Output HTML path (optional)")
    ui_parser.add_argument("--open", action="store_true", dest="open_browser", help="Open HTML after generation")
    ui_parser.add_argument(
        "--simple",
        action="store_true",
        help="Use legacy PyVis renderer instead of interactive template output",
    )

    return parser


def _run_ui(graph_json: str, *, output: str | None, open_browser: bool, simple: bool) -> int:
    json_path = Path(graph_json).resolve()
    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        return 2

    output_path = Path(output).resolve() if output else None
    try:
        output_path = render_graph_file(
            json_path,
            output_path=output_path,
            open_browser=open_browser,
            simple=simple,
        )
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON - {exc}", file=sys.stderr)
        return 2
    except RuntimeError:
        print("Error: pyvis not installed. Run: uv sync --extra simple", file=sys.stderr)
        return 1

    print(f"HTML viewer generated: {output_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    if args.command == "ui":
        return _run_ui(
            args.graph_json,
            output=args.output,
            open_browser=args.open_browser,
            simple=args.simple,
        )

    parser.print_help(sys.stderr)
    return 2
