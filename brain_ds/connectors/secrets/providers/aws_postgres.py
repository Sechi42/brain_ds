"""AWS Secrets Manager adapter for RDS Postgres connections.

boto3 is an OPTIONAL dependency (``pip install brain_ds[postgres]``).
It is imported lazily *inside* resolve/probe so the package imports
cleanly without it installed.

Persisted metadata keys:
  - ``secret_id``  (required): ARN or name of the AWS secret
  - ``database``   (required): database name — ALWAYS from metadata, NEVER
                               inferred from the AWS payload (Decision 2 / INV-2)
  - ``region``     (optional): defaults to boto3 credential-chain default;
                               us-east-2 is the project default for new handles

The resolved RDS JSON payload (username, password, host, port, …) is held
in-memory only — it is NEVER written to the manifest, the values file,
any log, or any API response body (INV-1/INV-2).
"""
from __future__ import annotations

import json
from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter

# fmt: off
_BOTO3_HINT = (
    "boto3 is not installed. "
    "Run `pip install brain_ds[postgres]` to enable AWS RDS Postgres resolution."
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


class AwsPostgresAdapter(SecretProviderAdapter):
    """Resolve RDS Postgres connection params from AWS Secrets Manager.

    The adapter fetches the ARN secret at connect time, parses the standard
    RDS JSON payload ({username, password, engine, host, port,
    dbClusterIdentifier, …}), and returns typed connection parameters.

    IMPORTANT — ``database`` is ALWAYS taken from handle metadata (the value
    the admin declared at registration), never from the AWS payload.  RDS
    secrets do not carry a reliable ``database`` key.

    Mirrors AwsSecretsAdapter exactly: same lazy boto3, same _ERROR_MAP,
    same INV-1/INV-2 invariants.
    """

    kind = "aws-postgres"
    # region is optional — boto3 falls back to AWS_DEFAULT_REGION / profile
    _REQUIRED = {"secret_id", "database"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message=f"missing required fields: {', '.join(sorted(missing))}"
            )

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Fetch RDS secret from AWS and return typed Postgres connection params.

        Returned dict: {host, port, username, password, database, sslmode, engine}.
        ``database`` is always from metadata[\"database\"] (INV-2).
        Callers MUST NOT persist or log any field containing credentials.
        """
        self.validate(metadata)
        boto3, botocore_exc = _lazy_boto3()

        region = metadata.get("region") or None
        secret_id = metadata["secret_id"]
        # INV-2: capture database from metadata BEFORE touching the AWS payload
        database = metadata["database"]

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
            payload: dict[str, Any] = json.loads(secret_string)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationError(
                message=(
                    "AWS secret value is not valid JSON. "
                    "RDS secrets must carry a JSON object with host/username/password."
                )
            ) from exc

        # Validate required RDS payload keys (extra keys are silently tolerated — INV-4)
        _PAYLOAD_REQUIRED = {"host", "username", "password"}
        missing_payload = _PAYLOAD_REQUIRED - set(payload)
        if missing_payload:
            key = next(iter(sorted(missing_payload)))
            raise ValidationError(
                message=(
                    f"AWS secret JSON missing required key '{key}'. "
                    "RDS secrets must carry host/username/password; "
                    "database is declared at registration."
                )
            )

        # INV-1: never log/persist password or any credential field
        return {
            "host": payload["host"],
            "port": int(payload.get("port", 5432)),
            "username": payload["username"],
            "password": payload["password"],      # ephemeral — caller must not persist
            "database": database,                  # INV-2: always from metadata
            "sslmode": payload.get("sslmode", "require"),
            "engine": payload.get("engine", "postgres"),
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Validate credentials + secret reachability without persisting the value.

        Performs a live get_secret_value call and parses the RDS JSON to verify
        that the credential chain and secret ARN are valid.  The retrieved value
        is discarded immediately.  Raises a friendly ValidationError on failure.
        """
        # resolve() already handles all validation, AWS call, and error mapping.
        # The returned dict is discarded — probe only verifies reachability.
        self.resolve(handle, metadata)
