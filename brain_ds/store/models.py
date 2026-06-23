"""Persistence row models for SQLite graph store."""

from __future__ import annotations

from dataclasses import dataclass


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
