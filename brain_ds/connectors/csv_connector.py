"""Read-only CSV/TSV connector.

Opens files with encoding="utf-8-sig" (handles BOM), sniffs the delimiter
automatically, and infers column types from the first 100 data rows.

Path sandbox: the file path must be validated via validate_path_within_root
before constructing this connector.

Google Sheets notes:
  Google Sheets exploration is delegated to the agent layer via MCP Google
  Drive read tools (mcp__claude_ai_Google_Drive__*). If a Sheet has been
  exported to CSV, use this connector on the exported file.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .base import ReadOnlyConnector

_PREVIEW_ROW_CAP = 50
_TYPE_SAMPLE_ROWS = 100


def _infer_type(values: list[str]) -> str:
    """Infer a simple type string from a sample of string values."""
    non_empty = [v for v in values if v.strip()]
    if not non_empty:
        return "TEXT"

    # Try integer
    try:
        for v in non_empty:
            int(v)
        return "INTEGER"
    except ValueError:
        pass

    # Try float
    try:
        for v in non_empty:
            float(v)
        return "REAL"
    except ValueError:
        pass

    return "TEXT"


class CsvConnector(ReadOnlyConnector):
    """Read-only connector for CSV and TSV files.

    The file is opened with encoding='utf-8-sig' to handle BOM-prefixed files
    exported from Excel. The delimiter is auto-detected via csv.Sniffer on the
    first 4 KB; falls back to comma if sniffing fails.

    Container model:
      - list_containers() returns [stem] — the filename without extension.
      - list_tables(stem) returns ["data"] — the single logical table.
      - get_table_schema / preview operate on that table.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).resolve()
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")

    def _detect_dialect(self) -> csv.Dialect | type[csv.Dialect]:
        with open(self._path, encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(4096)
        dialect: csv.Dialect | type[csv.Dialect]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel()
        return dialect

    def _read_rows(self, limit: int | None = None) -> tuple[list[str], list[list[str]]]:
        """Return (headers, rows) where rows are raw string lists."""
        dialect = self._detect_dialect()
        headers: list[str] = []
        rows: list[list[str]] = []
        with open(self._path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, dialect)
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                    continue
                rows.append(row)
                if limit is not None and len(rows) >= limit:
                    break
        return headers, rows

    def describe(self) -> dict[str, Any]:
        headers, _ = self._read_rows(limit=0)
        return {
            "kind": "csv",
            "path": str(self._path),
            "description": f"CSV/TSV file {self._path.name}",
            "size_bytes": self._path.stat().st_size,
            "column_count": len(headers),
        }

    def list_containers(self) -> list[str]:
        return [self._path.stem]

    def list_tables(self, container: str) -> list[str]:  # noqa: ARG002
        return ["data"]

    def get_table_schema(self, container: str, table: str) -> dict[str, Any]:  # noqa: ARG002
        headers, sample_rows = self._read_rows(limit=_TYPE_SAMPLE_ROWS)

        # Build column-indexed sample lists
        col_samples: dict[int, list[str]] = {i: [] for i in range(len(headers))}
        for row in sample_rows:
            for i, val in enumerate(row):
                if i < len(headers):
                    col_samples[i].append(val)

        columns = []
        for i, name in enumerate(headers):
            samples = col_samples.get(i, [])
            inferred_type = _infer_type(samples)
            first_sample = next((v for v in samples if v.strip()), None)
            columns.append({
                "name": name,
                "type": inferred_type,
                "sample": first_sample,
                "meaning": "",
            })

        return {
            "columns": columns,
            "row_count_estimate": len(sample_rows),  # at most _TYPE_SAMPLE_ROWS
        }

    def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:  # noqa: ARG002
        capped = min(max(1, limit), _PREVIEW_ROW_CAP)
        headers, rows = self._read_rows(limit=capped + 1)

        truncated = len(rows) > capped
        data_rows = rows[:capped]

        result_rows = []
        for row in data_rows:
            record = {}
            for i, col in enumerate(headers):
                record[col] = row[i] if i < len(row) else None
            result_rows.append(record)

        return {
            "columns": headers,
            "rows": result_rows,
            "truncated": truncated,
        }
