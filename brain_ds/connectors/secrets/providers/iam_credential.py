"""IAM credential secret provider adapter (validation-only)."""
from __future__ import annotations

import os
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class IamCredentialAdapter(SecretProviderAdapter):
    """Reference explicit AWS IAM credentials.

    Live AWS resolution is intentionally deferred to a follow-up slice; this
    adapter validates the metadata and resolves the ``access_key_id`` and the
    ``session_token`` (via ``session_token_ref``) from the local environment
    so a downstream connector can use them when wired in.
    """

    kind = "iam-credential"
    _REQUIRED = {"access_key_id", "session_token_ref"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message="missing required fields: " + ", ".join(sorted(missing))
            )
        access_key_id = metadata.get("access_key_id")
        if not isinstance(access_key_id, str) or not access_key_id.strip():
            raise ValidationError(message="access_key_id must be a non-empty string")
        session_token_ref = metadata.get("session_token_ref")
        if not isinstance(session_token_ref, str) or not session_token_ref.strip():
            raise ValidationError(message="session_token_ref must be a non-empty string")

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref")
        return {
            "access_key_id": metadata["access_key_id"],
            "session_token": os.environ[metadata["session_token_ref"]],
            "secret_access_key": os.environ[secret_ref] if secret_ref else None,
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Verify the referenced env-vars are present (live AWS deferred)."""
        self.validate(metadata)
        session_token_ref = metadata["session_token_ref"]
        if session_token_ref not in os.environ:
            raise ValidationError(message=f"session_token_ref {session_token_ref!r} is not set")
        secret_ref = metadata.get("secret_ref")
        if secret_ref and secret_ref not in os.environ:
            raise ValidationError(message=f"secret_ref {secret_ref!r} is not set")

