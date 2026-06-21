"""Shared secret redaction utility used by catalog, MCP tools, UI, and logs."""
from __future__ import annotations

from typing import Any

# Source: SI-6 — case-insensitive substring match against dict keys.
REDACTION_TOKENS: list[str] = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "access_key",
    "private_key",
    "client_secret",
    "service_account.private_key",
]

# Keys that match a redaction token by substring but are NOT secret values —
# they are references/labels safe to expose. ``secret_handle`` is the NAME an
# agent reads from a connection descriptor to drive explore_source; the real
# secret lives in AWS Secrets Manager, never in the handle name.
REDACTION_EXEMPT_KEYS: frozenset[str] = frozenset({"secret_handle"})


def _is_secret_key(key: str) -> bool:
    if key in REDACTION_EXEMPT_KEYS:
        return False
    lower = key.lower()
    return any(token in lower for token in REDACTION_TOKENS)


def redact_secrets(obj: Any, mask: str = "***") -> Any:
    """Recursively replace values whose key names match the redaction pattern.

    The key match is case-insensitive and applies to any substring, so
    ``password``, ``PASSWORD``, ``db_password``, and ``service_account.private_key``
    are all masked. Non-dict/list values are returned unchanged.
    """
    if isinstance(obj, dict):
        return {key: mask if _is_secret_key(key) else redact_secrets(value, mask) for key, value in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(item, mask) for item in obj]
    return obj
