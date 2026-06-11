from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import brain_ds.workspaces as workspace_registry
from brain_ds.mcp.security import ValidationError, resolve_store_path, validate_tool_input
from brain_ds.mcp.tools import TOOL_REGISTRY
from brain_ds.store.graph_store import GraphStore


class McpSession:
    """Mutable server-side session: open_workspace swaps the active store."""

    def __init__(self, project_root: Path, store: GraphStore):
        self.project_root = project_root
        self.store = store


def _open_session(project_root: Path) -> McpSession:
    canonical_root = project_root.resolve()
    store_existed = (canonical_root / ".brain_ds" / "store.db").exists()
    store_path = resolve_store_path(str(canonical_root))
    store = GraphStore(str(store_path), read_only=False)
    if store_existed:
        # Only pre-initialized workspaces enter the global registry; a cwd
        # fallback landing on a junk folder must not pollute the vault list.
        try:
            workspace_registry.register_workspace(canonical_root)
        except OSError:
            pass
    return McpSession(canonical_root, store)


def run_mcp_server(project_root: Path) -> None:
    _ensure_utf8_stdout()
    session = _open_session(project_root)

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                _write_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue

            request_id = request.get("id")
            method = request.get("method")

            # JSON-RPC notifications carry no id and MUST NOT receive a response.
            # Some clients (e.g. Claude Code, OpenCode) send
            # "notifications/initialized" after the initialize handshake; we
            # acknowledge by ignoring it.
            if request_id is None and isinstance(method, str) and method.startswith("notifications/"):
                continue

            if method == "initialize":
                _write_response(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                            "serverInfo": {"name": "brain_ds", "version": "0.1.0"},
                            "capabilities": {"tools": {"listChanged": False}},
                        },
                    }
                )
                continue

            if method == "tools/list":
                _write_response({"jsonrpc": "2.0", "id": request_id, "result": {"tools": _mcp_tools_list()}})
                continue

            if method == "tools/call":
                _write_response(_handle_tools_call(request_id, request.get("params", {}), session))
                continue

            _write_response({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
    finally:
        session.store.close()


def _handle_tools_call(request_id: Any, params: dict[str, Any], session: McpSession) -> dict[str, Any]:
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not isinstance(tool_name, str) or not tool_name:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: name is required"}}

    if not isinstance(arguments, dict):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "Invalid params: arguments must be an object"},
        }

    tool_meta = TOOL_REGISTRY.get(tool_name)
    if tool_meta is None:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

    # open_workspace mutates the session (store swap), so it cannot run through
    # the stateless tool handlers.
    if tool_name == "open_workspace":
        return _handle_open_workspace(request_id, arguments, session)

    try:
        result = tool_meta["handler"](session.store, arguments)
    except Exception:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": "Internal error"}}

    if isinstance(result, dict) and "code" in result and "message" in result:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": result["code"], "message": result["message"]},
        }

    return _tool_result(request_id, result)


def _handle_open_workspace(request_id: Any, arguments: dict[str, Any], session: McpSession) -> dict[str, Any]:
    try:
        validate_tool_input("open_workspace", arguments)
    except ValidationError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}}

    target = arguments["path"]
    entry = workspace_registry.find_workspace(target)
    if entry is None:
        registered = [item["path"] for item in workspace_registry.list_workspaces()]
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": (
                    f"Workspace not registered: {target}. Registered workspaces: "
                    f"{registered or 'none'}. Run 'brain_ds setup' in that folder or pick it in "
                    "the brain_ds desktop app, then retry."
                ),
            },
        }

    try:
        store_path = resolve_store_path(entry["path"])
        new_store = GraphStore(str(store_path), read_only=False)
    except Exception as exc:  # noqa: BLE001 — surface as JSON-RPC error, keep current store
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc) or "Internal error"}}

    session.store.close()
    session.store = new_store
    session.project_root = Path(entry["path"]).resolve()
    workspace_registry.register_workspace(session.project_root)

    result = {
        "project_root": str(session.project_root),
        "graphs": [asdict(meta) for meta in new_store.list_graphs()],
    }
    return _tool_result(request_id, result)


def _tool_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]},
    }


def _mcp_tools_list() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, meta in TOOL_REGISTRY.items():
        tools.append(
            {
                "name": name,
                "description": meta["description"],
                "inputSchema": meta["schema"],
            }
        )
    return tools


def _ensure_utf8_stdout() -> None:
    # Windows consoles default to cp1252; non-Latin payload chars would raise
    # UnicodeEncodeError at write time and kill the stdio loop.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _write_response(payload: dict[str, Any]) -> None:
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()
