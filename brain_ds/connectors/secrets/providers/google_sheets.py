"""Google Sheets JSON service-account adapter."""
from __future__ import annotations

import os
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class GoogleSheetsJsonAdapter(SecretProviderAdapter):
    """Reference a Google Sheets data source via service-account JSON."""

    kind = "google-sheets-json"
    _REQUIRED = {"spreadsheet_id", "sheet_range", "service_account_ref"}

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
        service_account_ref = metadata["service_account_ref"]
        return {
            "spreadsheet_id": metadata["spreadsheet_id"],
            "sheet_range": metadata["sheet_range"],
            "service_account_json": os.environ[service_account_ref],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Verify the referenced service-account env-var is present."""
        self.validate(metadata)
        service_account_ref = metadata["service_account_ref"]
        if service_account_ref not in os.environ:
            raise ValidationError(
                message=f"service_account_ref {service_account_ref!r} is not set"
            )
