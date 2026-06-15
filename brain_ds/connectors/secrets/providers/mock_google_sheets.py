"""Mock Google Sheets JSON provider for deterministic E2E fixtures.

This adapter mirrors the google-sheets-json metadata contract but never
contacts Google APIs.  The probe is a deterministic no-op so the explicit
``--probe`` path can be exercised in tests without real service-account keys.
"""
from __future__ import annotations

from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


class MockGoogleSheetsJsonAdapter(SecretProviderAdapter):
    """Fixture Google Sheets adapter for end-to-end secret anti-leak tests."""

    kind = "mock-google-sheets-json"
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
        return {
            "spreadsheet_id": metadata["spreadsheet_id"],
            "sheet_range": metadata["sheet_range"],
            "service_account_ref": metadata["service_account_ref"],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Fixture probe: validates metadata but never calls Google APIs."""
        self.validate(metadata)
