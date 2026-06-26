"""Persistence row models for SQLite graph store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(slots=True)
class GraphMeta:
    id: str
    workspace_root: str
    workspace_path: str
    project: str
    org: str
    schema_version: str
    contract_version: str
    node_count: int
    edge_count: int
    imported_from: str | None
    generated_at: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class NodeRow:
    graph_id: str
    id: str
    label: str
    type: str
    supertype: str | None
    details: dict
    card_sections: list | None
    editable_fields: list | None
    evidence_ids: list | None
    layout_hint: dict | None
    parent_id: str | None
    depth: int
    created_at: str
    modified_at: str


@dataclass(slots=True)
class EdgeRow:
    graph_id: str
    edge_id: str
    source: str
    target: str
    label: str
    weight: float | None
    reasons: list | None
    evidence_ids: list | None
    created_at: str


@dataclass(slots=True)
class EvidenceRow:
    graph_id: str
    id: str
    type: str
    source: str
    content: str
    provenance: dict | None
    timestamp: str | None


@dataclass(slots=True)
class ClusterRow:
    graph_id: str
    id: str
    name: str
    description: str | None
    parent_id: str | None
    metadata: dict | None
    created_at: str


@dataclass(slots=True)
class ClusterMemberRow:
    graph_id: str
    cluster_id: str
    node_id: str
    weight: float | None


@dataclass(slots=True)
class EmbeddingRow:
    id: int
    graph_id: str
    target_type: str
    target_id: str
    model: str
    dimensions: int
    vector: bytes
    created_at: str


@dataclass(slots=True)
class NearestHit:
    target_id: str
    score: float


@dataclass(slots=True)
class LedgerRow:
    """One append-only row in confidence_ledger.

    target_type is always 'edge' in Brick A; the column is forward-compatible
    with 'node' (future brick).  id defaults to None for new (un-inserted) rows;
    the repository sets it from lastrowid after INSERT.
    """

    id: int | None
    graph_id: str
    target_type: str          # 'edge' | 'node'
    target_id: str            # edge_id (or node id for future use)
    status: str               # inferred | needs-confirmation | confirmed | invalidated | abstain
    initial_confidence: float | None
    current_confidence: float | None
    relationship_label: str | None
    source_node_id: str | None
    target_node_id: str | None
    source_node_type: str | None
    target_node_type: str | None
    evidence_ids: list | None  # stored as JSON in DB
    captured_by: str | None   # 'mapper' | 'verifier' | 'human' | 'import'
    captured_at: str           # UTC ISO-8601
    confirmed_at: str | None
    confirmed_by: str | None
    flagged_reason: str | None
    gold_rationale: str | None
    provenance: str            # 'seed' | 'hand_labeled' | 'generated'
    # Node-fact descriptor fields (v7); NULL for edge rows.
    fact_label: str | None = None
    fact_path: str | None = None
    fact_value: str | None = None
    fact_subject_type: str | None = None


@dataclass(slots=True)
class PendingQuestionRow:
    """One deferred elicitation question stored outside the confidence ledger."""

    id: int
    graph_id: str
    target_node_id: str | None
    gap_kind: str
    entity_type: str | None
    question_text: str
    stakeholder_owner: str | None
    status: str
    created_at: str
    resolved_at: str | None
    resolved_by: str | None


@dataclass(slots=True)
class ClusterMetadataV1:
    """Typed contract for first-class semantic cluster metadata."""

    status: str = "proposed"
    primary_anchor_id: str | None = None
    primary_anchor_type: str | None = None
    dominant_department_id: str | None = None
    supporting_anchor_ids: list[str] | None = None
    needs_source: bool = True
    source_requirements: dict | None = None
    summary: str | None = None
    quality_signals: dict | None = None
    archived_reason: str | None = None

    VALID_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {"proposed", "confirmed", "incomplete", "needs-source", "rejected", "archived"}
    )
    VALID_ANCHOR_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"KPI", "Problem / Improvement Area", "Department"}
    )

    def __post_init__(self) -> None:
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported cluster status: {self.status}")
        if self.primary_anchor_type is not None and self.primary_anchor_type not in self.VALID_ANCHOR_TYPES:
            raise ValueError(f"Unsupported primary anchor type: {self.primary_anchor_type}")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "primary_anchor_id": self.primary_anchor_id,
            "primary_anchor_type": self.primary_anchor_type,
            "dominant_department_id": self.dominant_department_id,
            "supporting_anchor_ids": list(self.supporting_anchor_ids or []),
            "needs_source": bool(self.needs_source),
            "source_requirements": dict(self.source_requirements or {}),
            "summary": self.summary,
            "quality_signals": dict(self.quality_signals or {}),
            "archived_reason": self.archived_reason,
        }
