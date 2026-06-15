"""Abstract base for secret provider adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .catalog import SecretCatalog


class SecretProviderAdapter(ABC):
    """Resolve a secret handle to connection parameters without exposing raw values.

    Each adapter declares the provider ``kind`` it supports, validates the
    redacted metadata stored in the workspace manifest, and resolves the handle
    to connection parameters at connection time.
    """

    kind: str

    @abstractmethod
    def validate(self, metadata: dict[str, Any]) -> None:
        """Raise ValidationError if metadata is incomplete/invalid for this kind."""

    @abstractmethod
    def resolve(self, handle: str, catalog: "SecretCatalog") -> dict[str, Any]:
        """Return connection parameters. Raw secrets must never leave this layer."""
