from __future__ import annotations

import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from brain_ds.store.errors import StoreError


class SecurityError(Exception):
    """Raised when a security boundary is violated."""


class ValidationError(Exception):
    """JSON-RPC parameter validation error."""

    def __init__(self, code: int = -32602, message: str = "Invalid params"):
        self.code = code
        self.message = message
        super().__init__(message)


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "list_graphs": {
        "type": "object",
        "required": [],
        "properties": {},
        "additionalProperties": False,
    },
    "list_nodes": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "type": {"type": "string"},
            "supertype": {"type": "string"},
            "parent_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "get_node": {
        "type": "object",
        "required": ["graph_id", "node_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "search_graph": {
        "type": "object",
        "required": ["graph_id", "query"],
        "properties": {
            "graph_id": {"type": "string"},
            "query": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "update_node": {
        "type": "object",
        "required": ["graph_id", "node_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
            "label": {"type": "string"},
            "type": {"type": "string"},
            "details": {"type": "object"},
            "card_sections": {"type": "array"},
            "supertype": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "add_edge": {
        "type": "object",
        "required": ["graph_id", "source", "target", "label"],
        "properties": {
            "graph_id": {"type": "string"},
            "source": {"type": "string"},
            "target": {"type": "string"},
            "label": {"type": "string"},
            "weight": {"type": "number"},
            "reasons": {"type": "array"},
        },
        "additionalProperties": False,
    },
    # B1 context-return tools — zero-param empty-object schemas (matching list_graphs pattern).
    "run_elicit": {
        "type": "object",
        "required": [],
        "properties": {},
        "additionalProperties": False,
    },
    "map_connections": {
        "type": "object",
        "required": [],
        "properties": {},
        "additionalProperties": False,
    },
    "generate_brd": {
        "type": "object",
        "required": [],
        "properties": {},
        "additionalProperties": False,
    },
}


def resolve_store_path(project_root: str) -> Path:
    root_input = Path(project_root)
    if ".." in root_input.parts:
        raise SecurityError("Path traversal is not allowed")

    try:
        canonical_root = root_input.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SecurityError("Project root does not exist") from exc

    (canonical_root / ".brain_ds").mkdir(parents=True, exist_ok=True)
    store_path = canonical_root / ".brain_ds" / "store.db"
    resolved_store = store_path.resolve(strict=False)

    root_real = os.path.realpath(str(canonical_root))
    store_real = os.path.realpath(str(store_path))
    root_prefix = os.path.join(root_real, "")
    if not store_real.startswith(root_prefix):
        raise SecurityError("Store path escapes project root")

    try:
        resolved_store.relative_to(canonical_root)
    except ValueError as exc:
        raise SecurityError("Store path escapes canonical root") from exc

    return resolved_store


def validate_tool_input(tool_name: str, params: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    if schema is None:
        schema = TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        raise ValidationError(code=-32602, message=f"Unknown tool schema: {tool_name}")

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional = schema.get("additionalProperties", True)

    for name in required:
        if name not in params:
            raise ValidationError(code=-32602, message=f"Missing required parameter: {name}")

    if not additional:
        for name in params:
            if name not in properties:
                raise ValidationError(code=-32602, message=f"Unknown parameter: {name}")

    for name, value in params.items():
        if name not in properties:
            continue
        expected_type = properties[name].get("type")
        if expected_type is None:
            continue
        if not _matches_type(value, expected_type):
            raise ValidationError(code=-32602, message=f"Expected {expected_type} for {name}")

    return params


def error_boundary(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except ValidationError as exc:
            return {"code": exc.code, "message": exc.message}
        except StoreError:
            return {"code": -32000, "message": "Store operation failed"}
        except Exception:
            return {"code": -32000, "message": "Internal error"}

    return wrapped


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True
