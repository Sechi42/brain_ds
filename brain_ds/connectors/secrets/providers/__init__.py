"""Provider adapter registry for workspace secrets."""
from __future__ import annotations

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter
from .aws_postgres import AwsPostgresAdapter
from .aws_secrets import AwsSecretsAdapter
from .google_sheets import GoogleSheetsJsonAdapter
from .iam_credential import IamCredentialAdapter
from .iam_role import IamRoleAdapter
from .mock_google_sheets import MockGoogleSheetsJsonAdapter
from .mock_postgres import MockPostgresAdapter
from .postgres import PostgresAdapter
from .sqlite_secret import SqliteAdapter
from .sqlserver import SqlServerAdapter

__all__ = [
    "AwsPostgresAdapter",
    "AwsSecretsAdapter",
    "GoogleSheetsJsonAdapter",
    "IamCredentialAdapter",
    "IamRoleAdapter",
    "MockGoogleSheetsJsonAdapter",
    "MockPostgresAdapter",
    "PostgresAdapter",
    "SqliteAdapter",
    "SqlServerAdapter",
    "get_provider_adapter",
]

_ADAPTERS: dict[str, type] = {
    AwsPostgresAdapter.kind: AwsPostgresAdapter,
    PostgresAdapter.kind: PostgresAdapter,
    SqlServerAdapter.kind: SqlServerAdapter,
    AwsSecretsAdapter.kind: AwsSecretsAdapter,
    IamRoleAdapter.kind: IamRoleAdapter,
    IamCredentialAdapter.kind: IamCredentialAdapter,
    GoogleSheetsJsonAdapter.kind: GoogleSheetsJsonAdapter,
    SqliteAdapter.kind: SqliteAdapter,
    MockPostgresAdapter.kind: MockPostgresAdapter,
    MockGoogleSheetsJsonAdapter.kind: MockGoogleSheetsJsonAdapter,
}


def get_provider_adapter(kind: str) -> SecretProviderAdapter:
    """Return a fresh adapter instance for the given provider kind."""
    cls = _ADAPTERS.get(kind)
    if cls is None:
        raise ValidationError(message=f"unknown provider kind: {kind}")
    return cls()

