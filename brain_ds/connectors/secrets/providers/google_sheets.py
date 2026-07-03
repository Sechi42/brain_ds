"""Google Sheets JSON service-account adapter."""
from __future__ import annotations

import json
import os
from hashlib import sha256
from typing import Any

from brain_ds.connectors.google_sheets_api import parse_google_sheet_url
from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter


_SERVICE_ACCOUNT_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "auth_uri",
    "token_uri",
    "auth_provider_x509_cert_url",
    "client_x509_cert_url",
    "universe_domain",
)

RAW_VALUE_METADATA_KEY = "_raw_value"


def _load_service_account(raw_value: str) -> dict[str, Any]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValidationError(message="raw_value must be a non-empty service-account JSON string")
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValidationError(message="raw_value must be valid service-account JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError(message="raw_value must be a service-account JSON object")
    for field in _SERVICE_ACCOUNT_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise ValidationError(message=f"service-account JSON field '{field}' must be a non-empty string")
    if payload["type"] != "service_account":
        raise ValidationError(message="service-account JSON field 'type' must be service_account")
    return payload


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _build_sheets_service(service_account_info: dict[str, Any]) -> Any:
    try:
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from googleapiclient.discovery import build  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValidationError(
            message="google-api-python-client and google-auth are required to probe Google Sheets handles"
        ) from exc

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _google_probe_failure_message(exc: Exception) -> str:
    """Return a safe operator hint without echoing provider exception text."""
    status_code = getattr(exc, "status_code", None) or getattr(getattr(exc, "resp", None), "status", None)
    text = f"{type(exc).__name__} {status_code or ''}".lower()
    if status_code in (401, 403) or "permission" in text or "forbidden" in text:
        return (
            "Google Sheets probe failed: share the spreadsheet with the service-account "
            "email and confirm the Sheets API is enabled."
        )
    if status_code in (429, 500, 502, 503, 504) or "rate" in text or "timeout" in text:
        return "Google Sheets probe failed: Google returned a temporary error; retry later."
    if status_code == 404 or "notfound" in text or "not found" in text:
        return "Google Sheets probe failed: verify the spreadsheet URL and sharing settings."
    return "Google Sheets probe failed. Verify spreadsheet access and service-account permissions."


class GoogleSheetsJsonAdapter(SecretProviderAdapter):
    """Reference a Google Sheets data source via service-account JSON."""

    kind = "google-sheets-json"
    _REQUIRED = {"spreadsheet_id", "sheet_range"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message=f"missing required fields: {', '.join(sorted(missing))}"
            )
        has_legacy_env_ref = isinstance(metadata.get("service_account_ref"), str)
        has_uploaded_secret = metadata.get("credential_type") == "service_account" and isinstance(
            metadata.get("project_id"), str
        )
        if not has_legacy_env_ref and not has_uploaded_secret:
            raise ValidationError(
                message="google-sheets-json requires either legacy service_account_ref or uploaded service-account metadata"
            )

    def validate_upload(self, metadata: dict[str, Any], raw_value: str) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        service_account = _load_service_account(raw_value)
        url_parts = parse_google_sheet_url(str(metadata.get("spreadsheet_url", "")))
        sheet_range = metadata.get("sheet_range", "A1:Z")
        if not isinstance(sheet_range, str) or not sheet_range:
            raise ValidationError(message="sheet_range must be a non-empty string")
        redacted = {
            "spreadsheet_id": url_parts["spreadsheet_id"],
            "sheet_range": sheet_range,
            "credential_type": "service_account",
            "project_id": service_account["project_id"],
            "email_fingerprint": _fingerprint(service_account["client_email"]),
            "key_id_fingerprint": _fingerprint(service_account["private_key_id"]),
            "universe_domain": service_account["universe_domain"],
        }
        if "gid" in url_parts:
            redacted["gid"] = url_parts["gid"]
        self.validate(redacted)
        return redacted

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self.validate(metadata)
        raw_value = metadata.get(RAW_VALUE_METADATA_KEY)
        if isinstance(raw_value, str) and raw_value:
            return {
                "spreadsheet_id": metadata["spreadsheet_id"],
                "sheet_range": metadata["sheet_range"],
                "service_account_info": _load_service_account(raw_value),
                "use_direct_api": True,
            }
        service_account_ref = metadata["service_account_ref"]
        return {
            "spreadsheet_id": metadata["spreadsheet_id"],
            "sheet_range": metadata["sheet_range"],
            "service_account_json": os.environ[service_account_ref],
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
        """Verify the referenced service-account can read spreadsheet metadata."""
        self.validate(metadata)
        raw_value = metadata.get(RAW_VALUE_METADATA_KEY)
        if isinstance(raw_value, str) and raw_value:
            service_account = _load_service_account(raw_value)
            try:
                sheets = _build_sheets_service(service_account)
                response = (
                    sheets.spreadsheets()
                    .get(
                        spreadsheetId=metadata["spreadsheet_id"],
                        fields="spreadsheetId,properties.title",
                    )
                    .execute()
                )
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(
                    message=_google_probe_failure_message(exc)
                ) from exc
            return {
                "spreadsheet_id": str(response.get("spreadsheetId") or metadata["spreadsheet_id"]),
                "title": str((response.get("properties") or {}).get("title") or ""),
            }
        service_account_ref = metadata.get("service_account_ref")
        if not isinstance(service_account_ref, str) or service_account_ref not in os.environ:
            raise ValidationError(
                message=f"service_account_ref {service_account_ref!r} is not set"
            )
        return None
