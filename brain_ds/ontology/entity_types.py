"""Entity type ontology with supertypes and colors."""

from __future__ import annotations

from enum import Enum


class EntityType(Enum):
    ORGANIZATION = ("Organization", "actor", "#111827")
    DEPARTMENT = ("Department", "actor", "#2563eb")
    ROLE = ("Role", "actor", "#16a34a")
    DATA_SOURCE = ("Data Source", "data", "#7c3aed")
    HEURISTIC = ("Heuristic", "process", "#f59e0b")
    TACIT_KNOWLEDGE = ("Tacit Knowledge", "data", "#0ea5e9")
    PROBLEM_IMPROVEMENT_AREA = ("Problem / Improvement Area", "problem", "#dc2626")
    PROJECT = ("Project", "process", "#4f46e5")
    RISK = ("Risk", "risk", "#b91c1c")
    DECISION = ("Decision", "process", "#0f766e")
    KPI = ("KPI", "metric", "#a16207")
    SOLUTION = ("Solution", "solution", "#059669")
    UNKNOWN = ("Unknown", "problem", "#6b7280")

    def __new__(cls, value: str, supertype: str, color: str):
        obj = object.__new__(cls)
        obj._value_ = value
        obj._supertype = supertype
        obj._color = color
        return obj

    @property
    def supertype(self) -> str:
        return self._supertype

    @property
    def color(self) -> str:
        return self._color

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
