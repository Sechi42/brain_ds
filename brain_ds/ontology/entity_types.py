"""Entity type ontology with supertypes and colors."""

from __future__ import annotations

from enum import Enum


class EntityType(Enum):
    _supertype: str
    _color: str
    _expected_sections: tuple[str, ...]

    ORGANIZATION = ("Organization", "actor", "#111827", ("Overview", "Mission", "Members"))
    DEPARTMENT = ("Department", "actor", "#2563eb", ("Overview", "Responsibilities"))
    ROLE = ("Role", "actor", "#16a34a", ("Overview", "Responsibilities"))
    DATA_SOURCE = (
        "Data Source",
        "data",
        "#7c3aed",
        ("Overview", "Structure", "Columns / Fields", "Purpose", "Owner", "Refresh Cadence"),
    )
    HEURISTIC = ("Heuristic", "process", "#f59e0b", ("Overview", "Inputs", "Logic"))
    TACIT_KNOWLEDGE = ("Tacit Knowledge", "data", "#0ea5e9", ("Overview", "Context", "Capture Notes"))
    PROBLEM_IMPROVEMENT_AREA = ("Problem / Improvement Area", "problem", "#dc2626", ("Overview", "Impact", "Current State"))
    PROJECT = ("Project", "process", "#4f46e5", ("Overview", "Scope", "Status"))
    RISK = ("Risk", "risk", "#b91c1c", ("Overview", "Likelihood", "Mitigation"))
    DECISION = ("Decision", "process", "#0f766e", ("Overview", "Options", "Rationale"))
    KPI = ("KPI", "metric", "#a16207", ("Overview", "Definition", "Target"))
    SOLUTION = ("Solution", "solution", "#059669", ("Overview", "Approach", "Dependencies"))
    UNKNOWN = ("Unknown", "problem", "#6b7280", ())

    def __new__(cls, value: str, supertype: str, color: str, expected_sections: tuple[str, ...] = ()):
        obj = object.__new__(cls)
        obj._value_ = value
        obj._supertype = supertype
        obj._color = color
        obj._expected_sections = expected_sections
        return obj

    @property
    def supertype(self) -> str:
        return self._supertype

    @property
    def color(self) -> str:
        return self._color

    @property
    def expected_sections(self) -> list[str]:
        return list(self._expected_sections)

    @classmethod
    def from_string(cls, value: str | None) -> "EntityType":
        if value is None:
            return cls.UNKNOWN

        raw = str(value).strip()
        if not raw:
            return cls.UNKNOWN

        normalized = raw.lower().replace("_", " ").replace("-", " ")
        normalized = " ".join(normalized.split())

        aliases: dict[str, EntityType] = {
            "organization": cls.ORGANIZATION,
            "department": cls.DEPARTMENT,
            "role": cls.ROLE,
            "data source": cls.DATA_SOURCE,
            "datasource": cls.DATA_SOURCE,
            "heuristic": cls.HEURISTIC,
            "tacit knowledge": cls.TACIT_KNOWLEDGE,
            "problem / improvement area": cls.PROBLEM_IMPROVEMENT_AREA,
            "problem/improvement area": cls.PROBLEM_IMPROVEMENT_AREA,
            "problem improvement area": cls.PROBLEM_IMPROVEMENT_AREA,
            "project": cls.PROJECT,
            "risk": cls.RISK,
            "decision": cls.DECISION,
            "kpi": cls.KPI,
            "solution": cls.SOLUTION,
            "unknown": cls.UNKNOWN,
        }

        return aliases.get(normalized, cls.UNKNOWN)
