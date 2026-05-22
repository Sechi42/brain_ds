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
