"""Abstract base for secret provider adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
    def resolve(self, handle: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return connection parameters for trusted code.

        The returned dict is meant for internal connector use only; agent-facing
        surfaces receive redacted descriptors, never this result.
        """

    def probe(self, handle: str, metadata: dict[str, Any]) -> None:
        """Optional real connectivity probe. Adapters that support it override."""
        raise NotImplementedError(f"probe not implemented for {self.kind}")
