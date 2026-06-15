"""Mock Postgres provider for deterministic E2E fixtures.

This adapter mirrors the postgres metadata contract but never contacts the
network.  The probe is a deterministic no-op so the explicit ``--probe`` path
can be exercised in tests without real cloud credentials.
"""
from __future__ import annotations

from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class MockPostgresAdapter(SecretProviderAdapter):
    """Fixture Postgres adapter for end-to-end secret anti-leak tests."""

    kind = "mock-postgres"
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
        return {
            "host": metadata["host"],
            "port": metadata["port"],
            "database": metadata["database"],
            "username": metadata["username"],
            "sslmode": metadata["sslmode"],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Fixture probe: validates metadata but never opens a network socket."""
        self.validate(metadata)
