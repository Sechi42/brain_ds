"""Workspace-scoped secret catalog and provider adapters."""
from __future__ import annotations

from .base import SecretProviderAdapter
from .catalog import SecretCatalog, SecretEntry, SecretManifestError
from .providers import get_provider_adapter
from .redaction import redact_secrets

__all__ = [
    "SecretProviderAdapter",
    "SecretCatalog",
    "SecretEntry",
    "SecretManifestError",
    "get_provider_adapter",
    "redact_secrets",
]
