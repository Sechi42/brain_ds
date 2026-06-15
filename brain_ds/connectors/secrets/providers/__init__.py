"""Provider adapter registry for workspace secrets."""
from __future__ import annotations

from brain_ds.mcp.security import ValidationError

from .aws_secrets import AwsSecretsAdapter
from .google_sheets import GoogleSheetsJsonAdapter
from .postgres import PostgresAdapter
from .sqlserver import SqlServerAdapter

__all__ = [
    "AwsSecretsAdapter",
    "GoogleSheetsJsonAdapter",
    "PostgresAdapter",
    "SqlServerAdapter",
    "get_provider_adapter",
]

_ADAPTERS: dict[str, type] = {
    PostgresAdapter.kind: PostgresAdapter,
    SqlServerAdapter.kind: SqlServerAdapter,
    AwsSecretsAdapter.kind: AwsSecretsAdapter,
    GoogleSheetsJsonAdapter.kind: GoogleSheetsJsonAdapter,
}


def get_provider_adapter(kind: str) -> PostgresAdapter | SqlServerAdapter | AwsSecretsAdapter | GoogleSheetsJsonAdapter:
    """Return a fresh adapter instance for the given provider kind."""
    cls = _ADAPTERS.get(kind)
    if cls is None:
        raise ValidationError(message=f"unknown provider kind: {kind}")
    return cls()
