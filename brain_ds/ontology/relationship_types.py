"""Canonical relationship vocabulary."""

from __future__ import annotations

from enum import Enum


class RelationshipType(Enum):
    _description: str

    OWNS = ("owns", "Source owns target")
    USES = ("uses", "Source uses target")
    DEPENDS_ON = ("depends-on", "Source depends on target")
    BLOCKED_BY = ("blocked-by", "Source is blocked by target")
    CREATES_RISK = ("creates-risk", "Source creates risk for target")
    DECIDED_BY = ("decided-by", "Source is decided by target")
    MEASURED_BY = ("measured-by", "Source is measured by target")
    SHARED_WITH = ("shared-with", "Source is shared with target")
    OWNED_BY = ("owned-by", "Source is owned by target")
    ACCOUNTABLE = ("accountable", "Source is accountable for target")
    DEGRADED_BY = ("degraded-by", "Source is degraded by target")
    TARGETS = ("targets", "Source targets target")
    IMPROVES = ("improves", "Source improves target")
    RESOLVES = ("resolves", "Source resolves target")

    def __new__(cls, value: str, description: str):
        obj = object.__new__(cls)
        obj._value_ = value
        obj._description = description
        return obj

    @property
    def description(self) -> str:
        return self._description

    @classmethod
    def from_string(cls, value: str) -> "RelationshipType":
        for item in cls:
            if item.value == value:
                return item
        raise ValueError(f"Unknown relationship label: {value}")


BASE_WEIGHTS: dict[RelationshipType, float] = {
    RelationshipType.OWNS: 0.40,
    RelationshipType.USES: 0.55,
    RelationshipType.DEPENDS_ON: 0.60,
    RelationshipType.BLOCKED_BY: 0.65,
    RelationshipType.CREATES_RISK: 0.70,
    RelationshipType.DECIDED_BY: 0.45,
    RelationshipType.MEASURED_BY: 0.50,
    RelationshipType.SHARED_WITH: 0.35,
    RelationshipType.OWNED_BY: 0.40,
    RelationshipType.ACCOUNTABLE: 0.50,
    RelationshipType.DEGRADED_BY: 0.65,
    RelationshipType.TARGETS: 0.50,
    RelationshipType.IMPROVES: 0.60,
    RelationshipType.RESOLVES: 0.70,
}

# Backward-compatible lowercase alias requested by SDD tasks/design notes.
base_weights = BASE_WEIGHTS
