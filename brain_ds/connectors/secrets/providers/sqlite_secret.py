"""SQLite secret provider adapter (path-only, no credential)."""
from __future__ import annotations
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class SqliteAdapter(SecretProviderAdapter):
    """Reference a local SQLite database file.

    SQLite uses file-system access; there is no remote credential to resolve.
    This adapter validates the ``path`` metadata and passes the path through.
    """

    kind = "sqlite"
    _REQUIRED = {"path"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message="missing required fields: " + ", ".join(sorted(missing))
            )
        path = metadata.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValidationError(message="path must be a non-empty string")

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self.validate(metadata)
        return {"path": metadata["path"]}

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """SQLite uses local file access; existence is a probe signal but not required."""
        self.validate(metadata)

