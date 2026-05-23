from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from brain_ds.mcp.security import resolve_store_path
from brain_ds.mcp.tools import TOOL_REGISTRY
from brain_ds.store.graph_store import GraphStore


def run_mcp_server(project_root: Path) -> None:
    store_path = resolve_store_path(str(project_root))
    store = GraphStore(str(store_path), read_only=False)

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
                _write_response(_handle_tools_call(request_id, request.get("params", {}), store))
                continue

            _write_response({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
    finally:
        store.close()


def _handle_tools_call(request_id: Any, params: dict[str, Any], store: GraphStore) -> dict[str, Any]:
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

    try:
        result = tool_meta["handler"](store, arguments)
    except Exception:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": "Internal error"}}

    if isinstance(result, dict) and "code" in result and "message" in result:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": result["code"], "message": result["message"]},
        }

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


def _write_response(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
