from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Sequence

from brain_ds.mcp.config import generate_claude_config, generate_opencode_config
from brain_ds.mcp.security import SecurityError
from brain_ds.mcp.server import run_mcp_server
from brain_ds.validation import validate_graph

from .render_context import WorkspaceContext
from .server import run_server
from .viewer import render_graph_data, render_graph_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain_ds")
    subparsers = parser.add_subparsers(dest="command")

    ui_parser = subparsers.add_parser("ui", help="Render graph JSON as interactive HTML")
    ui_parser.add_argument("graph_json", nargs="?", help="Path to graph JSON (or '-' to read JSON from stdin)")
    ui_parser.add_argument("--root", dest="project_root", help="Workspace root path used for contract metadata")
    ui_parser.add_argument("--project-root", dest="project_root", help="Project root path for serve mode")
    ui_parser.add_argument("--port", type=int, default=8765, help="Serve port (default: 8765)")
    ui_parser.add_argument(
        "--probe",
        action="store_true",
        help="Bind an ephemeral localhost port, print READY, and exit (installer smoke check)",
    )
    ui_parser.add_argument("--output", help="Output HTML path (optional, or '-' for stdout)")
    ui_parser.add_argument("--open", action="store_true", dest="open_browser", help="Open HTML after generation")
    ui_parser.add_argument(
        "--simple",
        action="store_true",
        help="Use legacy PyVis renderer instead of interactive template output",
    )
    ui_parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass validation errors and render anyway (use with caution)",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate graph JSON and report semantic issues")
    validate_parser.add_argument("graph_json", help="Path to graph JSON")
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        help="Print safely normalized JSON to stdout (does not mutate the input file)",
    )

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP stdio server")
    mcp_parser.add_argument("--project-root", dest="project_root", help="Project root containing .brain_ds/store.db")
    mcp_parser.add_argument("mcp_command", nargs="?", choices=["print-config"], help="MCP utility command")
    mcp_parser.add_argument("--absolute", action="store_true", help="Resolve --project-root to an absolute path")
    mcp_parser.add_argument(
        "--format",
        choices=["claude", "opencode"],
        default="claude",
        help="Output format for print-config (default: claude)",
    )

    return parser


def _run_ui(
    graph_json: str,
    *,
    output: str | None,
    project_root: Path,
    open_browser: bool,
    simple: bool,
    force: bool,
) -> int:
    if open_browser and output == "-":
        print("Error: cannot use --open with --output -", file=sys.stderr)
        return 2

    if graph_json == "-":
        try:
            raw_data = sys.stdin.read()
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            print("Error: invalid UTF-8 from stdin", file=sys.stderr)
            return 2

        try:
            graph_dict = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON from stdin - {exc}", file=sys.stderr)
            return 2

        try:
            graph_path = project_root / "(stdin)"
            workspace = WorkspaceContext.from_root_and_graph(project_root, graph_path)
            output_path = render_graph_data(
                graph_dict,
                output_path=output,
                workspace=workspace,
                open_browser=open_browser,
                simple=simple,
                force=force,
            )
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON from stdin - {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except RuntimeError:
            print("Error: pyvis not installed. Run: uv sync --extra simple", file=sys.stderr)
            return 1

        print(f"HTML viewer generated: {output_path}")
        return 0

    json_path = Path(graph_json).resolve()
    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        return 2

    output_path = Path(output).resolve() if output else None
    try:
        workspace = WorkspaceContext.from_root_and_graph(project_root, json_path)
        output_path = render_graph_file(
            json_path,
            output_path=output_path,
            workspace=workspace,
            open_browser=open_browser,
            simple=simple,
            force=force,
        )
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON - {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError:
        print("Error: pyvis not installed. Run: uv sync --extra simple", file=sys.stderr)
        return 1

    print(f"HTML viewer generated: {output_path}")
    return 0


def _run_validate(graph_json: str, *, fix: bool) -> int:
    json_path = Path(graph_json).resolve()
    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        return 2

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON - {exc}", file=sys.stderr)
        return 2

    result = validate_graph(data)

    if fix:
        print(json.dumps(result.normalized, ensure_ascii=False, indent=2))
        return 0

    if result.errors:
        for error in result.errors:
            message = f"[{error.severity}] {error.path}: {error.message}"
            if error.suggestion:
                message = f"{message} ({error.suggestion})"
            print(message, file=sys.stderr)
        return 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    if args.command == "ui":
        project_root = Path(args.project_root).resolve() if args.project_root else Path(".").resolve()
        if args.probe:
            with socket.create_server(("127.0.0.1", 0)):
                print("READY")
            return 0

        if args.graph_json in (None, "serve"):
            run_server(project_root=project_root, port=args.port)
            return 0

        return _run_ui(
            args.graph_json,
            output=args.output,
            project_root=project_root,
            open_browser=args.open_browser,
            simple=args.simple,
            force=args.force,
        )

    if args.command == "validate":
        return _run_validate(args.graph_json, fix=args.fix)

    if args.command == "mcp":
        if args.mcp_command == "print-config":
            root_value = args.project_root if args.project_root is not None else "."
            if root_value == "":
                print("usage: brain_ds mcp print-config [--project-root PROJECT_ROOT] [--absolute]", file=sys.stderr)
                return 2

            root_path = Path(root_value)
            if not root_path.exists():
                print(f"Error: project root does not exist: {root_value}", file=sys.stderr)
                return 2

            try:
                if args.format == "opencode":
                    config = generate_opencode_config(root_path, absolute=args.absolute)
                else:
                    config = generate_claude_config(root_path, absolute=args.absolute)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 2

            json.dump(config, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

        project_root = args.project_root or os.environ.get("BRAIN_DS_PROJECT_ROOT")

        if not project_root:
            print("usage: brain_ds mcp [-h] [--project-root PROJECT_ROOT]", file=sys.stderr)
            return 2

        try:
            run_mcp_server(Path(project_root).resolve())
            return 0
        except SecurityError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    parser.print_help(sys.stderr)
    return 2
