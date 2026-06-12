"""Repair mojibake text persisted before the MCP stdin UTF-8 fix.

Payloads decoded as cp1252 on Windows stored strings like "actualizaciÃ³n"
instead of "actualización". This module reverses that corruption in-place
for every text column that carries user-facing content.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

# Byte sequences that only appear in UTF-8 text mis-decoded as cp1252/latin-1.
_MOJIBAKE_MARKERS = ("Ã", "Â", "â")

# (table, key columns, text columns to repair)
_REPAIR_TARGETS = (
    ("graphs", ("id",), ("project", "org", "imported_from")),
    ("nodes", ("graph_id", "id"), ("label", "details", "card_sections", "editable_fields")),
    ("edges", ("graph_id", "edge_id"), ("label", "reasons")),
    ("evidence", ("graph_id", "id"), ("source", "content", "provenance")),
    ("clusters", ("graph_id", "id"), ("name", "description", "metadata")),
)

_MAX_PASSES = 3  # double/triple encoded payloads collapse in <= 3 passes


@dataclass
class RepairReport:
    db_path: str
    dry_run: bool
    backup_path: str | None = None
    cells_repaired: int = 0
    samples: list[tuple[str, str, str]] = field(default_factory=list)


def looks_mojibake(text: str) -> bool:
    return any(marker in text for marker in _MOJIBAKE_MARKERS)


def _decode_once(text: str) -> str | None:
    for codec in ("cp1252", "latin-1"):
        try:
            return text.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return None


def repair_text(text: str) -> str:
    """Return the repaired string, or the input unchanged when not mojibake."""
    fixed = text
    for _ in range(_MAX_PASSES):
        if not looks_mojibake(fixed):
            break
        candidate = _decode_once(fixed)
        if candidate is None or candidate == fixed:
            break
        fixed = candidate
    return fixed


def repair_store(db_path: str | Path, dry_run: bool = False) -> RepairReport:
    """Repair every mojibake text cell in the store. Backs up the db first."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"store not found: {path}")

    report = RepairReport(db_path=str(path), dry_run=dry_run)
    if not dry_run:
        backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        report.backup_path = str(backup)

    conn = sqlite3.connect(str(path))
    try:
        for table, keys, columns in _REPAIR_TARGETS:
            key_cols = ", ".join(keys)
            col_list = ", ".join(columns)
            rows = conn.execute(f"SELECT {key_cols}, {col_list} FROM {table}").fetchall()
            for row in rows:
                key_values = row[: len(keys)]
                updates: dict[str, str] = {}
                for offset, column in enumerate(columns):
                    value = row[len(keys) + offset]
                    if not isinstance(value, str) or not looks_mojibake(value):
                        continue
                    fixed = repair_text(value)
                    if fixed != value:
                        updates[column] = fixed
                        if len(report.samples) < 20:
                            report.samples.append((f"{table}.{column}", value[:80], fixed[:80]))
                if not updates:
                    continue
                report.cells_repaired += len(updates)
                if not dry_run:
                    set_clause = ", ".join(f"{col} = ?" for col in updates)
                    where_clause = " AND ".join(f"{key} = ?" for key in keys)
                    conn.execute(
                        f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                        (*updates.values(), *key_values),
                    )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return report
