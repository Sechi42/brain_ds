"""Postgres secret provider adapter."""
from __future__ import annotations

import os
import socket
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class PostgresAdapter(SecretProviderAdapter):
    """Resolve a Postgres handle to connection parameters via env-var password."""

    kind = "postgres"
    _REQUIRED = {"host", "port", "database", "username", "sslmode"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message=f"missing required fields: {', '.join(sorted(missing))}"
            )

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref")
        if not secret_ref:
            raise ValidationError(message="missing secret_ref for credential resolution")
        return {
            "host": metadata["host"],
            "port": metadata["port"],
            "database": metadata["database"],
            "username": metadata["username"],
            "sslmode": metadata["sslmode"],
            "password": os.environ[secret_ref],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Attempt a real TCP connection to the configured host/port."""
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref")
        if not secret_ref or secret_ref not in os.environ:
            raise ValidationError(message=f"secret_ref {secret_ref!r} is not set")
        host = metadata["host"]
        port = metadata["port"]
        try:
            with socket.create_connection((host, port), timeout=5):
                pass
        except OSError as exc:
            raise ValidationError(message=f"probe failed for {handle}: {exc}") from exc
