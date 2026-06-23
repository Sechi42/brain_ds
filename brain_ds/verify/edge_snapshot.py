from __future__ import annotations

import base64
import json
from typing import Any

from brain_ds.store.models import EdgeRow

MAX_EDGE_SNAPSHOT_LIMIT = 500
DEFAULT_EDGE_SNAPSHOT_LIMIT = 50
EDGE_SNAPSHOT_ORDER = "label ASC, edge_id ASC"


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
