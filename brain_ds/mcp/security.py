from __future__ import annotations

import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ParamSpec, Protocol, TypeVar, cast

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
            "details_kind": {"type": "string"},
            "source_id": {"type": "string"},
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
            "parent_id": {"type": "string"},
            "depth": {"type": "integer"},
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
            "confidence": {"type": "number"},
            "reasons": {"type": "array"},
            "evidence": {"type": "array"},
        },
        "additionalProperties": False,
    },
    "delete_node": {
        "type": "object",
        "required": ["graph_id", "node_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "delete_edge": {
        "type": "object",
        "required": ["graph_id", "source", "target"],
        "properties": {
            "graph_id": {"type": "string"},
            "source": {"type": "string"},
            "target": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "create_graph": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "name": {"type": "string"},
            "project": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "import_graph": {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {"type": "string"},
            "graph_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "list_data_sources": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "suggest_connections": {
        "type": "object",
        "required": ["graph_id", "node_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
            "threshold": {"type": "number"},
            "limit": {"type": "integer"},
            "minimum_shared_tokens": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "assess_completeness": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "get_weak_edges": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "max_confidence": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "snapshot_edges": {
        "type": "object",
        "required": ["graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "source": {"type": "string"},
            "target": {"type": "string"},
            "label": {},
            "min_weight": {"type": "number"},
            "max_weight": {"type": "number"},
            "has_evidence": {"type": "boolean"},
            "neighborhood": {"type": "object"},
            "mode": {"type": "string"},
            "limit": {"type": "integer"},
            "cursor": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "list_workspaces": {
        "type": "object",
        "required": [],
        "properties": {
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
            "compact": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "open_workspace": {
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string"},
        },
        "additionalProperties": False,
    },
    # Read-only data source exploration tools
    "list_source_connections": {
        "type": "object",
        "required": [],
        "properties": {
            "graph_id": {"type": "string"},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
            "compact": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "explore_source": {
        "type": "object",
        "required": ["node_id", "graph_id"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
            "container": {"type": "string"},
            "table": {"type": "string"},
            "level": {"type": "string", "enum": ["source", "container", "table", "documentation", "internal"]},
        },
        "additionalProperties": False,
    },
    "query_source": {
        "type": "object",
        "required": ["node_id", "graph_id", "sql"],
        "properties": {
            "graph_id": {"type": "string"},
            "node_id": {"type": "string"},
            "sql": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    # Secret handle surface — admin-only; never returns raw values.
    "list_secret_handles": {
        "type": "object",
        "required": [],
        "properties": {
            "agent_scope": {"type": "string"},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
            "compact": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "validate_secret_handle": {
        "type": "object",
        "required": ["handle"],
        "properties": {
            "handle": {"type": "string"},
            "agent_scope": {"type": "string"},
            "probe": {"type": "boolean"},
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

_CARD_SECTION_ALLOWED_KEYS = {"title", "content", "icon", "order"}
P = ParamSpec("P")
R = TypeVar("R")


class WrappedHandler(Protocol[P, R]):
    __wrapped__: Callable[P, R]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]: ...


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


def validate_path_within_root(file_path: str, project_root: str | Path) -> Path:
    path_input = Path(file_path)
    if ".." in path_input.parts:
        raise SecurityError("Path traversal is not allowed")

    root_input = Path(project_root)
    canonical_root = root_input.resolve(strict=True)
    canonical_path = path_input.resolve(strict=True)

    root_real = os.path.realpath(str(canonical_root))
    path_real = os.path.realpath(str(canonical_path))
    root_prefix = os.path.join(root_real, "")
    if not path_real.startswith(root_prefix):
        raise SecurityError("Path traversal escapes project root")

    try:
        canonical_path.relative_to(canonical_root)
    except ValueError as exc:
        raise SecurityError("Path traversal escapes project root") from exc

    return canonical_path


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


def validate_card_sections(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValidationError(code=-32602, message="card_sections must be an array")

    validated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError(code=-32602, message="card_sections items must be objects")
        unknown_keys = [key for key in item if key not in _CARD_SECTION_ALLOWED_KEYS]
        if unknown_keys:
            allowed = ", ".join(["title", "content", "icon", "order"])
            raise ValidationError(
                code=-32602,
                message=f"Unknown card_sections key: {unknown_keys[0]}. Allowed keys: {allowed}",
            )
        missing = [key for key in ("title", "content") if key not in item]
        if missing:
            raise ValidationError(
                code=-32602,
                message=f"card_sections items require: {', '.join(missing)}",
            )
        validated.append(item)
    return validated


def is_workspace_admin(params: dict[str, Any]) -> None:
    """Fail-closed scope guard for secret-mutating MCP tools.

    The caller passes its claimed scope via ``agent_scope``; only
    ``workspace_admin`` is allowed. Scope failures raise ``SecurityError``
    (code -32001) to distinguish them from schema validation errors.
    """
    scope = params.get("agent_scope")
    if scope != "workspace_admin":
        raise SecurityError("requires workspace_admin")


def error_boundary(handler: Callable[P, R]) -> WrappedHandler[P, R]:
    @wraps(handler)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except SecurityError as exc:
            return {"code": -32001, "message": str(exc)}
        except ValidationError as exc:
            return {"code": exc.code, "message": exc.message}
        except StoreError:
            return {"code": -32000, "message": "Store operation failed"}
        except Exception:
            return {"code": -32000, "message": "Internal error"}

    return cast(WrappedHandler[P, R], wrapped)


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
