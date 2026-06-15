"""IAM role secret provider adapter (validation-only)."""
from __future__ import annotations

import os
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class IamRoleAdapter(SecretProviderAdapter):
    """Reference an assumable AWS IAM role.

    Live ``sts:AssumeRole`` is intentionally deferred to a follow-up slice;
    this adapter validates the metadata and resolves a placeholder credential
    ref so a downstream connector can attempt the assume-role when it is wired
    in. Treat the ``secret_ref`` as the env var that will hold the resolved
    session token.
    """

    kind = "iam-role"
    _REQUIRED = {"role_arn"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message="missing required fields: " + ", ".join(sorted(missing))
            )
        role_arn = metadata.get("role_arn")
        if not isinstance(role_arn, str) or not role_arn.startswith("arn:"):
            raise ValidationError(message="role_arn must be a string starting with `arn:`")

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref") or f"BRAINDS_{handle.upper()}_ROLE_TOKEN"
        return {
            "role_arn": metadata["role_arn"],
            "role_session_token": os.environ[secret_ref],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Verify the referenced env-var is present (live AWS deferred)."""
        self.validate(metadata)
        secret_ref = metadata.get("secret_ref") or f"BRAINDS_{handle.upper()}_ROLE_TOKEN"
        if secret_ref not in os.environ:
            raise ValidationError(message=f"secret_ref {secret_ref!r} is not set")

