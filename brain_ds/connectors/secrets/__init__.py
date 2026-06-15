"""Workspace-scoped secret catalog and provider adapters."""
from __future__ import annotations

from .base import SecretProviderAdapter
from .catalog import SecretCatalog, SecretEntry, SecretManifestError
from .redaction import redact_secrets

__all__ = [
    "SecretProviderAdapter",
    "SecretCatalog",
    "SecretEntry",
    "SecretManifestError",
    "redact_secrets",
]
