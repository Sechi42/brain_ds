from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from brain_ds.ontology import Graph
from brain_ds.validation import ValidationError, validate_graph

from .render_context import WorkspaceContext, build_render_context
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


def _format_validation_error(error: ValidationError) -> str:
    message = f"[{error.severity}] {error.path}: {error.message}"
    if error.suggestion:
        return f"{message} ({error.suggestion})"
    return message


def _validate_for_render(graph_dict: dict, *, force: bool) -> None:
    result = validate_graph(graph_dict)
    if not result.errors:
        return
    if force:
        return
    rendered_errors = "\n".join(_format_validation_error(error) for error in result.errors)
    raise ValueError(f"Validation failed:\n{rendered_errors}")


def derive_output_path(json_path: Path, graph: Graph) -> Path:
    return json_path.with_name(f"{slugify(str(graph.org or 'org'))}-graph.html")


def render_graph_file(
    json_path: Path,
    *,
    output_path: Path | None = None,
    workspace: WorkspaceContext | None = None,
    open_browser: bool = False,
    simple: bool = False,
    force: bool = False,
    network_cls: type | None = None,
) -> Path | str:
    with json_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    _validate_for_render(payload, force=force)
    graph = Graph.from_v1(payload)
    final_output = output_path or derive_output_path(json_path, graph)
    return render_graph_data(
        payload,
        output_path=final_output,
        workspace=workspace,
        open_browser=open_browser,
        simple=simple,
        force=force,
        network_cls=network_cls,
    )


def render_graph_data(
    graph_dict: dict,
    *,
    output_path: Path | str | None = None,
    workspace: WorkspaceContext | None = None,
    open_browser: bool = False,
    simple: bool = False,
    force: bool = False,
    network_cls: type | None = None,
) -> Path | str:
    _validate_for_render(graph_dict, force=force)
    graph = Graph.from_v1(graph_dict)

    if output_path == "-":
        if simple:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
            tmp_path = Path(tmp_file.name)
            tmp_file.close()
            try:
                render_simple_html(
                    graph,
                    output_path=tmp_path,
                    open_browser=False,
                    network_cls=network_cls,
                )
                sys.stdout.write(tmp_path.read_text(encoding="utf-8"))
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            context = build_render_context(graph, workspace=workspace)
            html = render_interactive_html(context)
            sys.stdout.write(html)
        return "-"

    if output_path:
        final_output = Path(output_path)
    elif workspace is not None:
        final_output = workspace.store_path.parent / "graph-output.html"
    else:
        final_output = Path(".").resolve() / "graph-output.html"
    final_output.parent.mkdir(parents=True, exist_ok=True)

    if simple:
        return render_simple_html(
            graph,
            output_path=final_output,
            open_browser=open_browser,
            network_cls=network_cls,
        )

    context = build_render_context(graph, workspace=workspace)
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
    parser.add_argument("graph_json", help="Path to graph JSON (or '-' for stdin)")
    parser.add_argument("--output", help="Output HTML path (optional, or '-' for stdout)")
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

    output = "-" if args.output == "-" else (Path(args.output).resolve() if args.output else None)
    if args.open_browser and output == "-":
        print("Error: cannot use --open with --output -", file=sys.stderr)
        return 2
    try:
        output_path = render_graph_file(
            json_path,
            output_path=output,
            open_browser=args.open_browser,
            simple=args.simple,
            force=False,
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
