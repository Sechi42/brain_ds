"""AWS Secrets Manager reference adapter."""
from __future__ import annotations

import os
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class AwsSecretsAdapter(SecretProviderAdapter):
    """Reference an AWS Secrets Manager secret by region and secret_id.

    Live AWS resolution is deferred to a follow-up slice; this adapter resolves
    the referenced secret value from a local env-var when available.
    """

    kind = "aws-secrets"
    _REQUIRED = {"region", "secret_id"}

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
        secret_ref = metadata.get("secret_ref") or f"BRAINDS_{handle.upper()}_SECRET"
        return {
            "region": metadata["region"],
            "secret_id": metadata["secret_id"],
            "secret_value": os.environ[secret_ref],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Verify the referenced env-var is present (live AWS deferred)."""
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref") or f"BRAINDS_{handle.upper()}_SECRET"
        if secret_ref not in os.environ:
            raise ValidationError(message=f"secret_ref {secret_ref!r} is not set")
