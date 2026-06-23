from __future__ import annotations

import base64
import json
from typing import Any

from brain_ds.store.models import EdgeRow

MAX_EDGE_SNAPSHOT_LIMIT = 500
DEFAULT_EDGE_SNAPSHOT_LIMIT = 50
EDGE_SNAPSHOT_ORDER = "label ASC, edge_id ASC"

# Large-graph guard: graphs with more than this many edges require an explicit
# limit, mode, or filter when called without any narrowing signal.
LARGE_GRAPH_EDGE_THRESHOLD = 100_000

# Payload cap: snapshot responses must not exceed 256 KiB.
MAX_SNAPSHOT_PAYLOAD_BYTES = 256 * 1024  # 256 KiB


def encode_cursor(*, mode: str, last_label: str, last_edge_id: str) -> str:
    payload = {
        "mode": mode,
        "last_label": last_label,
        "last_edge_id": last_edge_id,
        "order": EDGE_SNAPSHOT_ORDER,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - normalized for MCP caller
        raise ValueError("invalid_cursor") from exc
    if not isinstance(decoded, dict) or decoded.get("order") != EDGE_SNAPSHOT_ORDER:
        raise ValueError("invalid_cursor")
    return decoded


def normalize_limit(limit: int | None) -> int:
    value = DEFAULT_EDGE_SNAPSHOT_LIMIT if limit is None else int(limit)
    if value < 1 or value > MAX_EDGE_SNAPSHOT_LIMIT:
        raise ValueError("limit must be between 1 and 500")
    return value


def validate_neighborhood(neighborhood: dict[str, Any] | None) -> None:
    if neighborhood is None:
        return
    depth = int(neighborhood.get("depth", 1))
    if depth < 1 or depth > 3:
        raise ValueError("neighborhood depth must be between 1 and 3")


def enforce_large_graph_guard(
    total_edge_count: int,
    *,
    has_explicit_limit: bool,
    has_explicit_mode: bool,
    has_filter: bool,
) -> None:
    """Raise ValueError('limit_required') for unbounded large-graph calls.

    When a graph has more than ``LARGE_GRAPH_EDGE_THRESHOLD`` edges (>100k),
    calls that provide no explicit ``limit``, no explicit ``mode``, and no
    narrowing filter are rejected with ``ValueError('limit_required')`` so the
    MCP layer can map this to a ``400 limit_required`` response.

    Callers with any of the three narrowing signals are allowed through.

    Parameters
    ----------
    total_edge_count:
        Total number of edges in the graph (before any filter is applied).
    has_explicit_limit:
        True when the caller supplied a ``limit`` parameter explicitly.
    has_explicit_mode:
        True when the caller supplied a ``mode`` parameter explicitly (i.e. not
        relying on the default ``"sample"`` fallback).
    has_filter:
        True when the caller supplied at least one narrowing filter (``source``,
        ``target``, ``label``, ``min_weight``, ``max_weight``, ``has_evidence``,
        or ``neighborhood``).
    """
    if (
        total_edge_count > LARGE_GRAPH_EDGE_THRESHOLD
        and not has_explicit_limit
        and not has_explicit_mode
        and not has_filter
    ):
        raise ValueError("limit_required")


def enforce_payload_size_guard(payload: dict[str, Any]) -> None:
    """Raise ValueError('payload_too_large') when the serialised payload exceeds 256 KiB.

    The snapshot payload is serialised to JSON and its byte length is checked
    against ``MAX_SNAPSHOT_PAYLOAD_BYTES`` (256 KiB).  If the serialised size
    exceeds the cap this helper raises so the MCP layer can truncate or reject.

    Parameters
    ----------
    payload:
        The snapshot dict that will be returned to the caller.
    """
    serialised = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(serialised) > MAX_SNAPSHOT_PAYLOAD_BYTES:
        raise ValueError("payload_too_large")


def _edge_to_snapshot(edge: EdgeRow) -> dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "source": edge.source,
        "target": edge.target,
        "label": edge.label,
        "weight": edge.weight,
        "reasons": edge.reasons or [],
        "evidence_ids": edge.evidence_ids or [],
        "deterministic_flags": _deterministic_flags(edge),
    }


def _deterministic_flags(edge: EdgeRow) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if not edge.evidence_ids:
        flags.append(
            {
                "code": "missing_evidence",
                "dimension": "edge_evidence",
                "severity": "SUGGESTION",
                "message": "Edge has no cited evidence.",
            }
        )
    if edge.weight is None or edge.weight < 0 or edge.weight > 1:
        flags.append(
            {
                "code": "weight_out_of_range",
                "dimension": "edge_weight",
                "severity": "SUGGESTION",
                "message": "Edge weight must be between 0 and 1.",
            }
        )
    return flags


def _rank(edges: list[EdgeRow], mode: str) -> list[EdgeRow]:
    if mode == "evidence_ranked":
        return sorted(
            edges,
            key=lambda edge: (
                bool(edge.evidence_ids),
                -(len(edge.evidence_ids or [])),
                edge.weight or 0.0,
                edge.edge_id,
            ),
        )
    if mode == "calibration":
        return sorted(
            edges,
            key=lambda edge: (
                edge.label,
                edge.weight if edge.weight is not None else 1.0,
                edge.edge_id,
            ),
        )
    return sorted(edges, key=lambda edge: (edge.label, edge.edge_id))


def build_edge_snapshot(
    *,
    graph_id: str,
    edges: list[EdgeRow],
    mode: str,
    limit: int | None,
    neighborhood: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_limit = normalize_limit(limit)
    validate_neighborhood(neighborhood)
    ranked = _rank(edges, mode)
    page = ranked[:resolved_limit]
    next_cursor = None
    if len(ranked) > resolved_limit and page:
        last = page[-1]
        next_cursor = encode_cursor(mode=mode, last_label=last.label, last_edge_id=last.edge_id)
    return {
        "graph_id": graph_id,
        "mode": mode,
        "order": EDGE_SNAPSHOT_ORDER,
        "limit": resolved_limit,
        "next_cursor": next_cursor,
        "edges": [_edge_to_snapshot(edge) for edge in page],
    }
