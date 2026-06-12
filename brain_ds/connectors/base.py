"""Abstract base class for read-only data-source connectors.

The ReadOnlyConnector interface enforces the read-only contract at the API
surface level: no write methods exist on the interface. There is no write path
to bypass or override.

Implementations must be safe to instantiate multiple times for the same source
without side-effects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ReadOnlyConnector(ABC):
    """Read-only connector interface for external data sources.

    All methods return plain Python objects (dicts, lists) for easy JSON
    serialisation. None of them mutate the underlying source.
    """

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return source-level metadata.

        Returns a dict with at minimum:
          - kind: connector type string (e.g. "sqlite", "csv")
          - path: resolved absolute path string
          - description: human-readable summary
        Additional keys are connector-specific.
        """

    @abstractmethod
    def list_containers(self) -> list[str]:
        """Return top-level containers (schemas, sheets, etc.).

        For SQLite: returns schema names (e.g. ["main"]).
        For CSV: returns a single entry — the file name without extension.
        """

    @abstractmethod
    def list_tables(self, container: str) -> list[str]:
        """Return table/sheet names within the given container.

        For SQLite: returns table and view names in the schema.
        For CSV: the container is the file stem; returns ["data"] as the sole table.
        """

    @abstractmethod
    def get_table_schema(self, container: str, table: str) -> dict[str, Any]:
        """Return schema information for a table/sheet.

        Returns a dict with:
          - columns: list of {name, type, sample, meaning} dicts
            - name: column name
            - type: declared or inferred type string
            - sample: first non-null sample value (stringified) or None
            - meaning: empty string (connectors do not infer business meaning)
          - row_count_estimate: integer (exact for small tables, -1 if unknown)
        """

    @abstractmethod
    def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:
        """Return a row preview for a table/sheet.

        The limit parameter is capped at 50 by all implementations.
        Returns a dict with:
          - columns: list of column name strings
          - rows: list of row dicts (column name -> value)
          - truncated: bool — True if more rows exist beyond limit
        """
