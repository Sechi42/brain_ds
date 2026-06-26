"""Pure DTOs for query-first business dossier routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_BUSINESS_DOSSIER_LIMIT = 50
MAX_BUSINESS_ALTERNATIVES = 3


@dataclass(frozen=True, slots=True)
class BusinessDossierRequest:
    graph_id: str
    query: str
    limit: int = 10
    max_alternatives: int = MAX_BUSINESS_ALTERNATIVES
    create_pending_questions: bool = False
    stakeholder_owner: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", self.query.strip())
        object.__setattr__(self, "limit", _clamp_int(self.limit, minimum=1, maximum=MAX_BUSINESS_DOSSIER_LIMIT))
        object.__setattr__(
            self,
            "max_alternatives",
            _clamp_int(self.max_alternatives, minimum=1, maximum=MAX_BUSINESS_ALTERNATIVES),
        )
        object.__setattr__(self, "create_pending_questions", self.create_pending_questions is True)
        object.__setattr__(self, "stakeholder_owner", self.stakeholder_owner.strip())


@dataclass(frozen=True, slots=True)
class BusinessInterpretation:
    id: str
    label: str
    entity_type: str
    entity_ids: tuple[str, ...] | list[str] = ()
    evidence_ids: tuple[str, ...] | list[str] = ()
    confidence: float = 0.0
    rationale: str = ""
    is_default: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "confidence", _unit(self.confidence))


@dataclass(frozen=True, slots=True)
class BusinessUncertainty:
    source_heavy: bool = False
    business_light: bool = False
    completeness: list[dict[str, Any]] = field(default_factory=list)
    currency: list[dict[str, Any]] = field(default_factory=list)
    weak_edges: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    truncation_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PendingQuestionProposal:
    target_node_id: str
    gap_kind: str
    entity_type: str
    question_text: str
    stakeholder_owner: str = ""
    evidence_ids: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(frozen=True, slots=True)
class BusinessDossier:
    query: str
    selected_interpretation_id: str
    interpretations: list[BusinessInterpretation] = field(default_factory=list)
    dossier: dict[str, Any] = field(default_factory=dict)
    evidence_sources: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: BusinessUncertainty = field(default_factory=BusinessUncertainty)
    pending_question_proposals: list[PendingQuestionProposal] = field(default_factory=list)
    pending_questions_created: list[dict[str, Any]] = field(default_factory=list)
    serialized_for_llm: str = ""


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _unit(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
