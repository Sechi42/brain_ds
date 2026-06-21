"""AWS Secrets Manager adapter for Google Sheets service-account connections.

boto3 is an OPTIONAL dependency (``pip install brain_ds[aws]``).
gspread is an OPTIONAL dependency (``pip install brain_ds[gsheets]``).
Both are imported lazily *inside* resolve/probe so the package imports
cleanly without them installed.

Persisted metadata keys:
  - ``secret_id``      (required): ARN or name of the AWS secret holding the SA JSON
  - ``spreadsheet_id`` (required): Google Sheets spreadsheet ID (handle metadata)
  - ``sheet_range``    (required): default cell range (handle metadata, e.g. ``Sheet1!A1:Z``)
  - ``region``         (optional): defaults to boto3 credential-chain default;
                                   us-east-2 is the project default for new handles

The ARN secret value is the full service-account JSON object (all 11 SA fields).
It is held in-memory only — it is NEVER written to the manifest, the values file,
any log, or any API response body (INV-1).

spreadsheet_id and sheet_range come EXCLUSIVELY from handle metadata (INV-2).
"""
from __future__ import annotations

import json
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter

# fmt: off
_BOTO3_HINT = (
    "boto3 is not installed. "
    "Run `pip install brain_ds[aws]` to enable AWS Secrets Manager resolution."
)

_GSPREAD_HINT = (
    "gspread is not installed. "
    "Run `pip install brain_ds[gsheets]` to enable Google Sheets probe/exploration."
)
# fmt: on

_ERROR_MAP: dict[str, str] = {
    "AccessDeniedException": "Access denied to the AWS secret. Check IAM permissions.",
    "ResourceNotFoundException": (
        "AWS secret not found. Verify the secret_id (ARN or name) and region."
    ),
    "InvalidRequestException": "Invalid AWS Secrets Manager request. Check secret_id format.",
    "DecryptionFailure": "AWS could not decrypt the secret. Check KMS key permissions.",
    "InternalServiceError": "AWS Secrets Manager returned an internal error. Retry later.",
}


def _lazy_boto3():
    """Import boto3 and botocore lazily; raise ValidationError with install hint if absent."""
    try:
        import boto3  # type: ignore[import-untyped]
        import botocore.exceptions  # type: ignore[import-untyped]

        return boto3, botocore.exceptions
    except ImportError:
        raise ValidationError(message=_BOTO3_HINT)


def _lazy_gspread():
    """Import gspread lazily; raise ValidationError with install hint if absent."""
    try:
        import gspread  # type: ignore[import-untyped]

        return gspread
    except ImportError:
        raise ValidationError(message=_GSPREAD_HINT)


class AwsGoogleSheetsAdapter(SecretProviderAdapter):
    """Resolve Google Sheets service-account credentials from AWS Secrets Manager.

    The adapter fetches the ARN secret at connect time, parses the full
    service-account JSON payload (all 11 standard SA fields), and returns
    typed connection parameters.

    IMPORTANT — ``spreadsheet_id`` and ``sheet_range`` are ALWAYS taken from
    handle metadata (the values the admin declared at registration), never from
    the AWS payload (INV-2).

    Mirrors AwsPostgresAdapter exactly: same lazy boto3, same _ERROR_MAP,
    same INV-1/INV-2 invariants.
    """

    kind = "aws-google-sheets"
    # region is optional — boto3 falls back to AWS_DEFAULT_REGION / profile
    _REQUIRED = {"secret_id", "spreadsheet_id", "sheet_range"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message=f"missing required fields: {', '.join(sorted(missing))}"
            )

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Fetch service-account JSON from AWS and return typed Google Sheets params.

        Returned dict:
          - ``service_account_info``: full SA JSON dict (all 11 standard fields pass through)
          - ``spreadsheet_id``: from metadata (INV-2)
          - ``sheet_range``: from metadata (INV-2)

        Callers MUST NOT persist or log any field containing credentials.
        """
        self.validate(metadata)
        boto3, botocore_exc = _lazy_boto3()

        region = metadata.get("region") or None
        secret_id = metadata["secret_id"]
        # INV-2: capture spreadsheet_id + sheet_range from metadata BEFORE touching the AWS payload
        spreadsheet_id = metadata["spreadsheet_id"]
        sheet_range = metadata["sheet_range"]

        try:
            client = boto3.client("secretsmanager", region_name=region)
            response = client.get_secret_value(SecretId=secret_id)
        except botocore_exc.NoCredentialsError:
            raise ValidationError(
                message=(
                    "No local AWS credentials found. "
                    "Configure ~/.aws/credentials or set AWS_ACCESS_KEY_ID."
                )
            )
        except botocore_exc.PartialCredentialsError:
            raise ValidationError(
                message=(
                    "Incomplete AWS credentials. "
                    "Check that both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set."
                )
            )
        except botocore_exc.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            friendly = _ERROR_MAP.get(code, f"AWS error ({code}). Check your configuration.")
            raise ValidationError(message=friendly) from exc

        secret_string = response.get("SecretString") or ""
        try:
            sa: dict[str, Any] = json.loads(secret_string)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationError(
                message=(
                    "AWS secret value is not valid JSON. "
                    "Google Sheets secrets must carry a service-account JSON object."
                )
            ) from exc

        # INV-1: never log/persist the SA JSON or any credential field
        return {
            "service_account_info": sa,           # full SA dict, ephemeral only
            "spreadsheet_id": spreadsheet_id,     # INV-2: always from metadata
            "sheet_range": sheet_range,           # INV-2: always from metadata
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Validate the service-account JSON via gspread (no live spreadsheet call).

        Calls ``gspread.service_account_from_dict(sa)`` to verify that the
        credential parses to a valid gspread client.  No live fetch is made.
        Raises a friendly ValidationError on failure.
        """
        params = self.resolve(handle, metadata)
        sa = params["service_account_info"]

        gspread = _lazy_gspread()
        try:
            gspread.service_account_from_dict(sa)
        except Exception as exc:
            raise ValidationError(
                message=(
                    f"Google Sheets service-account JSON is invalid: {exc}. "
                    "Verify the SA JSON stored in AWS Secrets Manager."
                )
            ) from exc
