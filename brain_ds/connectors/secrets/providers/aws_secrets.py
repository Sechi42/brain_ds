"""AWS Secrets Manager reference adapter.

boto3 is an OPTIONAL dependency (``pip install brain_ds[aws]``).  It is
imported lazily *inside* resolve/probe so the package imports cleanly without
it installed.  ``region`` is optional in the handle metadata; when absent,
boto3 uses the local credential-chain default (AWS_DEFAULT_REGION / profile).

Persisted metadata keys: ``secret_id`` (required) and ``region`` (optional).
The resolved secret value is held in-memory only — it is NEVER written to the
manifest, the values file, any log, or any API response body (INV-1/INV-2).
"""
from __future__ import annotations

from typing import Any

from brain_ds.mcp.security import ValidationError

from ..base import SecretProviderAdapter

# fmt: off
_BOTO3_HINT = (
    "boto3 is not installed. "
    "Run `pip install brain_ds[aws]` to enable live AWS Secrets Manager resolution."
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
    """Import boto3 and botocore lazily; raise ValidationError if not installed."""
    try:
        import boto3  # type: ignore[import-untyped]
        import botocore.exceptions  # type: ignore[import-untyped]
        return boto3, botocore.exceptions
    except ImportError:
        raise ValidationError(message=_BOTO3_HINT)


class AwsSecretsAdapter(SecretProviderAdapter):
    """Resolve secrets from AWS Secrets Manager via the local credential chain.

    Handle persists only ``region`` (optional) and ``secret_id``.
    Live resolution is performed at query time via boto3; no raw value is
    stored or logged at any point.
    """

    kind = "aws-secrets"
    # region is optional — boto3 falls back to AWS_DEFAULT_REGION / profile
    _REQUIRED = {"secret_id"}

    def validate(self, metadata: dict[str, Any]) -> None:
        if not isinstance(metadata, dict):
            raise ValidationError(message="metadata must be an object")
        missing = self._REQUIRED - set(metadata)
        if missing:
            raise ValidationError(
                message=f"missing required fields: {', '.join(sorted(missing))}"
            )

    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Call AWS Secrets Manager and return the secret value IN-MEMORY ONLY.

        The returned dict contains ``secret_value`` (the live secret string),
        ``region``, and ``secret_id``.  Callers MUST NOT persist or log
        ``secret_value``.
        """
        self.validate(metadata)
        boto3, botocore_exc = _lazy_boto3()

        region = metadata.get("region") or None
        secret_id = metadata["secret_id"]

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

        secret_value = response.get("SecretString") or response.get("SecretBinary", b"").decode()
        # secret_value is ephemeral: returned to the immediate caller only,
        # never written, never logged (INV-1/INV-2).
        return {
            "region": metadata.get("region"),
            "secret_id": secret_id,
            "secret_value": secret_value,
        }

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Validate credentials + secret reachability without returning the value.

        Performs a live get_secret_value call to verify the credential chain
        and secret ARN are valid.  The retrieved value is discarded immediately.
        Raises a friendly ValidationError on any expected failure.
        """
        self.validate(metadata)
        boto3, botocore_exc = _lazy_boto3()

        region = metadata.get("region") or None
        secret_id = metadata["secret_id"]

        try:
            client = boto3.client("secretsmanager", region_name=region)
            client.get_secret_value(SecretId=secret_id)
            # Value discarded — probe only verifies reachability
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
