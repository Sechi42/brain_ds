from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ValidationError:
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"
    suggestion: str | None = None


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict = field(default_factory=dict)
