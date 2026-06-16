"""Pure data-source schema change-detection helpers (Work-Unit E).

This module is read-only and side-effect free. It computes a canonical schema
hash, resolves a verdict against a stored baseline, and produces a
Reflexion-style delta describing WHAT changed. It has NO graph dependency and
NO connector write capability — the baseline is persisted ONLY to the brain_ds
graph (via update_node) by the caller, never to the source.

Verdicts:
  - "new":              node has a connection, no baseline, no prior doc.
  - "unchanged":        baseline hash == freshly computed hash.
  - "changed":          baseline existed AND hashes differ (delta computed).
  - "unknown-baseline": node has prior doc/card_sections but NO baseline
                        (deployed before this feature). Self-heals on next pass.

Canonicalization eliminates cosmetic differences so reordering columns,
widening a varchar, or using a type synonym never produces a false "changed":
  - columns sorted by name; tables sorted by name
  - column name lowercased + stripped
  - type normalized to a coarse class (int/text/real/bool/timestamp/blob)
  - display length/precision dropped (varchar(255) -> text)
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

__all__ = [
    "canonicalize_schema",
    "compute_schema_hash",
    "compute_schema_delta",
    "resolve_verdict",
    "build_change_detection",
    "should_emit_change_detection",
    "VERDICTS",
]

VERDICTS: tuple[str, ...] = ("new", "unchanged", "changed", "unknown-baseline")

# Type-synonym map: each entry collapses raw SQL/CSV type spellings to a coarse
# class. Display length/precision (the (...) suffix) is stripped before lookup
# so varchar(100) and varchar(255) both reduce to "text".
_TYPE_SYNONYMS: dict[str, str] = {
    # integers
    "int": "int", "integer": "int", "int2": "int", "int4": "int", "int8": "int",
    "smallint": "int", "bigint": "int", "tinyint": "int", "mediumint": "int",
    "serial": "int", "bigserial": "int",
    # text
    "text": "text", "varchar": "text", "char": "text", "nchar": "text",
    "nvarchar": "text", "character": "text", "clob": "text", "string": "text",
    "varying": "text",
    # real / numeric
    "real": "real", "double": "real", "float": "real", "numeric": "real",
    "decimal": "real", "money": "real", "double precision": "real",
    # boolean
    "bool": "bool", "boolean": "bool",
    # temporal
    "datetime": "timestamp", "timestamp": "timestamp", "date": "timestamp",
    "time": "timestamp", "timestamptz": "timestamp",
    # binary
    "blob": "blob", "bytea": "blob", "binary": "blob", "varbinary": "blob",
}


def normalize_type(raw_type: str | None) -> str:
    """Reduce a declared/inferred type string to a coarse, stable class."""
    if not raw_type:
        return "unknown"
    t = str(raw_type).strip().lower()
    # drop display length/precision, e.g. "varchar(255)" -> "varchar",
    # "decimal(10,2)" -> "decimal".
    t = re.sub(r"\s*\(.*?\)\s*", "", t)
    t = t.strip()
    if not t:
        return "unknown"
    if t in _TYPE_SYNONYMS:
        return _TYPE_SYNONYMS[t]
    # handle multi-word types like "double precision" / "character varying"
    head = t.split()[0]
    if head in _TYPE_SYNONYMS:
        return _TYPE_SYNONYMS[head]
    return t


def _normalize_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def _iter_tables(schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract a {table_name: [column_dicts]} mapping from a live-schema dict.

    Accepts the multi-table shape ``{"tables": {name: {"columns": [...]}}}``
    and the single-table connector shape ``{"columns": [...]}`` (in which case
    the implicit table name is "data"). None-safe.
    """
    if not isinstance(schema, dict):
        return {}
    tables = schema.get("tables")
    if isinstance(tables, dict):
        out: dict[str, list[dict[str, Any]]] = {}
        for name, body in tables.items():
            cols = (body or {}).get("columns") if isinstance(body, dict) else None
            out[str(name)] = list(cols or [])
        return out
    columns = schema.get("columns")
    if isinstance(columns, list):
        return {"data": list(columns)}
    return {}


def canonicalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical, cosmetic-free representation of a live schema.

    Columns are reduced to ``{name, type}`` with normalized name + type class,
    sorted by name. Tables are sorted by name.
    """
    raw_tables = _iter_tables(schema)
    canon_tables: dict[str, Any] = {}
    for table_name in raw_tables.keys():
        cols = raw_tables[table_name]
        canon_cols = [
            {"name": _normalize_name(c.get("name")), "type": normalize_type(c.get("type"))}
            for c in cols
            if isinstance(c, dict)
        ]
        canon_cols.sort(key=lambda c: c["name"])
        # Table names keep their original spelling (stripped) for readable
        # deltas/snapshots, but are ordered case-insensitively for hash stability.
        canon_tables[str(table_name).strip()] = {"columns": canon_cols}
    ordered = {
        k: canon_tables[k]
        for k in sorted(canon_tables.keys(), key=lambda n: (n.lower(), n))
    }
    return {"tables": ordered}


def compute_schema_hash(schema: dict[str, Any]) -> str:
    """Return the hex sha256 over the canonicalized schema."""
    canonical = canonicalize_schema(schema)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _columns_by_table(canonical: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Map table -> {column_name: type_class} from a canonical schema."""
    result: dict[str, dict[str, str]] = {}
    for table, body in (canonical.get("tables") or {}).items():
        result[table] = {c["name"]: c["type"] for c in (body.get("columns") or [])}
    return result


def compute_schema_delta(
    baseline_snapshot: dict[str, Any],
    live_canonical: dict[str, Any],
) -> dict[str, list[Any]]:
    """Compute a Reflexion-style delta between a baseline snapshot and live schema.

    Both inputs must already be canonical (see ``canonicalize_schema``). Returns
    five lists: added_columns, removed_columns, altered_columns, added_tables,
    removed_tables.
    """
    base = _columns_by_table(baseline_snapshot or {"tables": {}})
    live = _columns_by_table(live_canonical or {"tables": {}})

    base_tables = set(base.keys())
    live_tables = set(live.keys())

    added_tables = sorted(live_tables - base_tables)
    removed_tables = sorted(base_tables - live_tables)

    added_columns: list[dict[str, str]] = []
    removed_columns: list[dict[str, str]] = []
    altered_columns: list[dict[str, str]] = []

    for table in sorted(base_tables & live_tables):
        base_cols = base[table]
        live_cols = live[table]
        for name in sorted(set(live_cols) - set(base_cols)):
            added_columns.append({"table": table, "name": name, "type": live_cols[name]})
        for name in sorted(set(base_cols) - set(live_cols)):
            removed_columns.append({"table": table, "name": name, "type": base_cols[name]})
        for name in sorted(set(base_cols) & set(live_cols)):
            if base_cols[name] != live_cols[name]:
                altered_columns.append({
                    "table": table,
                    "name": name,
                    "from_type": base_cols[name],
                    "to_type": live_cols[name],
                })

    return {
        "added_columns": added_columns,
        "removed_columns": removed_columns,
        "altered_columns": altered_columns,
        "added_tables": added_tables,
        "removed_tables": removed_tables,
    }


def resolve_verdict(
    *,
    live_hash: str,
    baseline: dict[str, Any] | None,
    has_prior_doc: bool,
) -> str:
    """Resolve the change-detection verdict. None-safe (E-REQ-11)."""
    baseline_hash = (baseline or {}).get("schema_hash") if isinstance(baseline, dict) else None
    if baseline_hash:
        return "unchanged" if baseline_hash == live_hash else "changed"
    # no usable baseline hash
    if has_prior_doc:
        return "unknown-baseline"
    return "new"


def should_emit_change_detection(*, level: str) -> bool:
    """Change detection is emitted ONLY at level == "table" (E-T2 guard)."""
    return level == "table"


def build_change_detection(
    *,
    live_schema: dict[str, Any],
    baseline: dict[str, Any] | None,
    has_prior_doc: bool,
) -> dict[str, Any]:
    """Compute the full ``change_detection`` block for a table-level exploration.

    The delta is present ONLY when verdict == "changed".
    """
    live_canonical = canonicalize_schema(live_schema)
    live_hash = compute_schema_hash(live_schema)
    verdict = resolve_verdict(live_hash=live_hash, baseline=baseline, has_prior_doc=has_prior_doc)

    last_documented_at = (baseline or {}).get("last_documented_at") if isinstance(baseline, dict) else None

    delta: dict[str, list[Any]] | None = None
    if verdict == "changed":
        snapshot = (baseline or {}).get("documented_schema_snapshot") or {"tables": {}}
        delta = compute_schema_delta(snapshot, live_canonical)

    return {
        "verdict": verdict,
        "schema_hash": live_hash,
        "last_documented_at": last_documented_at,
        "delta": delta,
    }


def build_baseline(live_schema: dict[str, Any], *, last_documented_at: str) -> dict[str, Any]:
    """Build the baseline object to persist on a Data Source node's details.

    Returned dict is stored under ``details["schema_baseline"]`` via update_node.
    This is a GRAPH write performed by the caller — never a source write.
    """
    return {
        "schema_hash": compute_schema_hash(live_schema),
        "documented_schema_snapshot": canonicalize_schema(live_schema),
        "last_documented_at": last_documented_at,
    }
