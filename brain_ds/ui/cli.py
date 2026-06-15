from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Sequence

from brain_ds.connectors.secrets import (
    SecretCatalog,
    SecretEntry,
    SecretManifestError,
    get_provider_adapter,
)
from brain_ds.mcp.config import generate_claude_config, generate_opencode_config
from brain_ds.mcp.security import SecurityError, ValidationError
from brain_ds.mcp.server import run_mcp_server
from brain_ds.validation import validate_graph

from .render_context import WorkspaceContext
from .server import run_server
from .setup import setup_main
from .viewer import render_graph_data, render_graph_file


def _resolve_ui_project_root(project_root_arg: str | None) -> Path:
    if project_root_arg:
        return Path(project_root_arg).resolve()
    env_root = os.environ.get("BRAIN_DS_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(".").resolve()


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

    setup_parser = subparsers.add_parser("setup", help="Configure brain_ds MCP clients for this project")
    setup_parser.add_argument(
        "--project-root",
        default=".",
        help="Project root used for store and MCP config generation (default: .)",
    )
    setup_parser.add_argument(
        "--agent",
        choices=["claude", "opencode", "both"],
        default="both",
        help="Which agent config(s) to write (default: both)",
    )
    setup_parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    setup_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt before writing")

    check_parser = subparsers.add_parser(
        "check",
        help="Verify the agent harness is installed and aligned for Claude Code and OpenCode",
    )
    check_parser.add_argument(
        "--project-root",
        default=".",
        help="Project root to check (default: .)",
    )

    secret_parser = subparsers.add_parser(
        "secret",
        help="Manage workspace-scoped secret handles",
    )
    secret_sub = secret_parser.add_subparsers(dest="secret_command")

    secret_list_parser = secret_sub.add_parser("list", help="List secret handles")
    secret_list_parser.add_argument(
        "--project-root",
        default=".",
        help="Project root containing .brain_ds/secrets.json (default: .)",
    )

    secret_add_parser = secret_sub.add_parser("add", help="Add or update a secret handle")
    secret_add_parser.add_argument("--project-root", default=".", help="Project root (default: .)")
    secret_add_parser.add_argument("--kind", required=True, help="Provider kind")
    secret_add_parser.add_argument("--handle", required=True, help="Unique handle name")
    secret_add_parser.add_argument(
        "--metadata-json",
        required=True,
        help="JSON object with provider metadata (never the raw secret value)",
    )
    value_group = secret_add_parser.add_mutually_exclusive_group(required=True)
    value_group.add_argument(
        "--value-stdin", action="store_true", help="Read the raw secret value from stdin"
    )
    value_group.add_argument(
        "--value-env", help="Name of the environment variable holding the raw secret value"
    )
    value_group.add_argument(
        "--value-file", help="Path to a file containing the raw secret value"
    )

    secret_remove_parser = secret_sub.add_parser("remove", help="Remove a secret handle")
    secret_remove_parser.add_argument("--project-root", default=".", help="Project root (default: .)")
    secret_remove_parser.add_argument("--handle", required=True, help="Handle to remove")

    secret_validate_parser = secret_sub.add_parser(
        "validate", help="Validate all secret handles against their provider schema"
    )
    secret_validate_parser.add_argument(
        "--project-root", default=".", help="Project root (default: .)"
    )
    mode_group = secret_validate_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Validate metadata only (default)",
    )
    mode_group.add_argument(
        "--probe",
        action="store_true",
        help="Also attempt real provider connectivity (explicit opt-in)",
    )

    return parser, secret_parser


def _run_setup(args: argparse.Namespace) -> int:
    return setup_main(args)


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
            rendered_output = render_graph_data(
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

        print(f"HTML viewer generated: {rendered_output}")
        return 0

    json_path = Path(graph_json).resolve()
    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        return 2

    render_output: Path | str | None = "-" if output == "-" else (Path(output).resolve() if output else None)
    try:
        workspace = WorkspaceContext.from_root_and_graph(project_root, json_path)
        rendered_output = render_graph_file(
            json_path,
            output_path=render_output if isinstance(render_output, Path) else None,
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

    print(f"HTML viewer generated: {rendered_output}")
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


def _load_catalog(project_root: Path) -> SecretCatalog:
    catalog = SecretCatalog(project_root)
    catalog.load()
    return catalog


def _read_raw_value(args: argparse.Namespace) -> str:
    if args.value_stdin:
        return sys.stdin.read().rstrip("\r\n")
    if args.value_env:
        try:
            return os.environ[args.value_env]
        except KeyError as exc:
            raise ValueError(f"environment variable {args.value_env!r} is not set") from exc
    if args.value_file:
        path = Path(args.value_file).resolve()
        return path.read_text(encoding="utf-8")
    raise ValueError("no value source specified")


def _run_secret_list(args: argparse.Namespace) -> int:
    try:
        catalog = _load_catalog(_resolve_ui_project_root(args.project_root))
    except SecretManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    entries = catalog.list_handles()
    if not entries:
        print("No secret handles found.")
        return 0

    print(f"{'handle':<20} {'kind':<20} {'created_at'}")
    for entry in entries:
        created_at = entry.created_at or ""
        print(f"{entry.handle:<20} {entry.kind:<20} {created_at}")
    return 0


def _run_secret_add(args: argparse.Namespace) -> int:
    try:
        metadata = json.loads(args.metadata_json)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid metadata JSON - {exc}", file=sys.stderr)
        return 2

    if not isinstance(metadata, dict):
        print("Error: metadata JSON must be an object", file=sys.stderr)
        return 2

    try:
        raw_value = _read_raw_value(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    project_root = _resolve_ui_project_root(args.project_root)
    catalog = SecretCatalog(project_root)
    try:
        catalog.load()
    except SecretManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    entry = SecretEntry(handle=args.handle, kind=args.kind, metadata=metadata)
    catalog.add(entry, raw_value=raw_value)
    print(f"Added secret handle {args.handle} ({args.kind})")
    return 0


def _run_secret_remove(args: argparse.Namespace) -> int:
    try:
        catalog = _load_catalog(_resolve_ui_project_root(args.project_root))
    except SecretManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    catalog.remove(args.handle)
    print(f"Removed secret handle {args.handle}")
    return 0


def _run_secret_validate(args: argparse.Namespace) -> int:
    try:
        catalog = _load_catalog(_resolve_ui_project_root(args.project_root))
    except SecretManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = catalog.validate_all()

    for entry in catalog.list_handles():
        try:
            adapter = get_provider_adapter(entry.kind)
            adapter.validate(entry.metadata)
            if args.probe:
                adapter.probe(entry.handle, entry.metadata)
        except ValidationError as exc:
            errors.append(f"{entry.handle}: {exc}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    if args.probe:
        print("All secret handles are valid and reachable.")
    else:
        print("All secret handles are valid (dry-run).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser, secret_parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    if args.command == "ui":
        project_root = _resolve_ui_project_root(args.project_root)
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

        # Same precedence as the UI: flag → env → cwd. The cwd fallback is what
        # lets a single global MCP entry follow the folder each session runs in.
        project_root_arg = args.project_root or os.environ.get("BRAIN_DS_PROJECT_ROOT") or str(Path.cwd())

        try:
            run_mcp_server(Path(project_root_arg).resolve())
            return 0
        except SecurityError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    if args.command == "setup":
        return _run_setup(args)

    if args.command == "check":
        from brain_ds.harness_check import harness_check_main

        return harness_check_main(Path(args.project_root))

    if args.command == "secret":
        if args.secret_command == "list":
            return _run_secret_list(args)
        if args.secret_command == "add":
            return _run_secret_add(args)
        if args.secret_command == "remove":
            return _run_secret_remove(args)
        if args.secret_command == "validate":
            return _run_secret_validate(args)
        secret_parser.print_help(sys.stderr)
        return 2

    parser.print_help(sys.stderr)
    return 2
