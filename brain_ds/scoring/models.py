"""Scoring result and context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrengthResult:
    weight: float
    reasons: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ScoringContext:
    edge_source: str
    edge_target: str
    relation_type: str
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
