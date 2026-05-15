"""Graph dataclasses and ontology-driven mappings."""

from __future__ import annotations

from dataclasses import dataclass, field

from .entity_types import EntityType
from .relationship_types import RelationshipType


@dataclass
class EvidenceRecord:
    id: str
    type: str
    source: str
    content: str
    provenance: dict[str, str] | None = None
    timestamp: str = ""


@dataclass
class CardSection:
    title: str
    content: str
    icon: str = ""
    order: int = 0


@dataclass
class Node:
    id: str
    label: str
    type: EntityType | str
    details: dict[str, str] = field(default_factory=dict)
    supertype: str | None = None
    card_sections: list[CardSection] | None = None
    evidence_ids: list[str] | None = None
    editable_fields: list[str] | None = None
    layout_hint: dict | None = None

    def __post_init__(self) -> None:
        if isinstance(self.type, EntityType):
            return
        self.type = EntityType.from_string(self.type)


@dataclass
class Edge:
    source: str
    target: str
    label: RelationshipType | str
    weight: float | None = None
    reasons: list[str] | None = None
    evidence_ids: list[str] | None = None
    edge_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.label, RelationshipType):
            return
        self.label = RelationshipType.from_string(self.label)


@dataclass
class Graph:
    schema_version: str = "2.0.0"
    org: str = ""
    generated_at: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        def serialize_node(node: Node) -> dict:
            payload = {
                "id": node.id,
                "label": node.label,
                "type": node.type.value,
                "details": node.details,
                "supertype": node.supertype if node.supertype is not None else node.type.supertype,
            }
            if node.card_sections is not None:
                payload["card_sections"] = [
                    {
                        "title": section.title,
                        "content": section.content,
                        "icon": section.icon,
                        "order": section.order,
                    }
                    for section in node.card_sections
                ]
            if node.evidence_ids is not None:
                payload["evidence_ids"] = node.evidence_ids
            if node.editable_fields is not None:
                payload["editable_fields"] = node.editable_fields
            if node.layout_hint is not None:
                payload["layout_hint"] = node.layout_hint
            return payload

        def serialize_edge(edge: Edge) -> dict:
            payload = {
                "source": edge.source,
                "target": edge.target,
                "label": edge.label.value,
            }
            if edge.weight is not None:
                payload["weight"] = edge.weight
            if edge.reasons is not None:
                payload["reasons"] = edge.reasons
            if edge.evidence_ids is not None:
                payload["evidence_ids"] = edge.evidence_ids
            if edge.edge_id is not None:
                payload["edge_id"] = edge.edge_id
            return payload

        def serialize_evidence(item: EvidenceRecord) -> dict:
            payload = {
                "id": item.id,
                "type": item.type,
                "source": item.source,
                "content": item.content,
                "timestamp": item.timestamp,
            }
            if item.provenance is not None:
                payload["provenance"] = item.provenance
            return payload

        return {
            "schema_version": self.schema_version,
            "org": self.org,
            "generated_at": self.generated_at,
            "nodes": [serialize_node(node) for node in self.nodes],
            "edges": [serialize_edge(edge) for edge in self.edges],
            "evidence": [serialize_evidence(item) for item in self.evidence],
        }

    @classmethod
    def from_v1(cls, data: dict, *, strict: bool = True) -> "Graph":
        _ = strict
        nodes = [
            Node(
                id=node["id"],
                label=node["label"],
                type=node["type"],
                details=node.get("details", {}),
                supertype=node.get("supertype"),
                card_sections=(
                    [CardSection(**section) for section in node["card_sections"]]
                    if node.get("card_sections") is not None
                    else None
                ),
                evidence_ids=node.get("evidence_ids"),
                editable_fields=node.get("editable_fields"),
                layout_hint=node.get("layout_hint"),
            )
            for node in data.get("nodes", [])
        ]
        edges = [
            Edge(
                source=edge["source"],
                target=edge["target"],
                label=edge["label"],
                weight=edge.get("weight"),
                reasons=edge.get("reasons"),
                evidence_ids=edge.get("evidence_ids"),
                edge_id=edge.get("edge_id"),
            )
            for edge in data.get("edges", [])
        ]
        evidence = [
            EvidenceRecord(
                id=item["id"],
                type=item["type"],
                source=item["source"],
                content=item["content"],
                provenance=item.get("provenance"),
                timestamp=item.get("timestamp", ""),
            )
            for item in data.get("evidence", [])
        ]
        return cls(
            schema_version=data.get("schema_version", "2.0.0"),
            org=data.get("org", ""),
            generated_at=data.get("generated_at", ""),
            nodes=nodes,
            edges=edges,
            evidence=evidence,
        )


TYPE_COLORS = {entity.value: entity.color for entity in EntityType}
TYPE_TO_SUPERTYPE = {entity.value: entity.supertype for entity in EntityType}
