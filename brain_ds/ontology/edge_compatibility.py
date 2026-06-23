"""Deterministic edge compatibility rules for ontology relationships."""

from __future__ import annotations

from dataclasses import dataclass

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType

EdgeCompatibilityStatus = str


@dataclass(frozen=True)
class EdgeCompatibilityVerdict:
    status: EdgeCompatibilityStatus
    source_supertype: str
    target_supertype: str
    relationship: str
    matrix_key: str
    reason: str


EDGE_COMPATIBILITY: dict[tuple[str, str, str], EdgeCompatibilityStatus] = {
    ("actor", RelationshipType.OWNS.value, "solution"): "valid",
    ("actor", RelationshipType.OWNS.value, "process"): "valid",
    ("actor", RelationshipType.OWNS.value, "data"): "valid",
    ("actor", RelationshipType.OWNS.value, "metric"): "valid",
    ("actor", RelationshipType.ACCOUNTABLE.value, "risk"): "valid",
    ("actor", RelationshipType.ACCOUNTABLE.value, "process"): "valid",
    ("metric", RelationshipType.MEASURED_BY.value, "data"): "valid",
    ("data", RelationshipType.USES.value, "data"): "valid",
    ("process", RelationshipType.USES.value, "data"): "valid",
    ("solution", RelationshipType.DEPENDS_ON.value, "solution"): "suspect",
    ("process", RelationshipType.DEPENDS_ON.value, "data"): "valid",
    ("process", RelationshipType.BLOCKED_BY.value, "risk"): "valid",
    ("process", RelationshipType.CREATES_RISK.value, "risk"): "valid",
    ("decision", RelationshipType.DECIDED_BY.value, "actor"): "valid",
    ("data", RelationshipType.SHARED_WITH.value, "actor"): "valid",
    ("data", RelationshipType.OWNED_BY.value, "actor"): "valid",
    ("metric", RelationshipType.DEGRADED_BY.value, "risk"): "valid",
    ("solution", RelationshipType.TARGETS.value, "problem"): "valid",
    ("solution", RelationshipType.IMPROVES.value, "metric"): "valid",
    ("solution", RelationshipType.RESOLVES.value, "problem"): "valid",
    ("risk", RelationshipType.OWNS.value, "actor"): "invalid",
}


def classify_edge_compatibility(
    source_type: str | EntityType, target_type: str | EntityType, label: str
) -> EdgeCompatibilityVerdict:
    """Classify an edge using ontology supertypes and a relationship matrix.

    Unknown entity types or legacy relationship labels are suspect, never fatal.
    """

    source_supertype = _coerce_entity_type(source_type).supertype
    target_supertype = _coerce_entity_type(target_type).supertype
    relationship = str(label)
    matrix_key = f"{source_supertype}.{relationship}.{target_supertype}"

    try:
        canonical_relationship = RelationshipType.from_string(relationship).value
    except ValueError:
        return EdgeCompatibilityVerdict(
            status="suspect",
            source_supertype=source_supertype,
            target_supertype=target_supertype,
            relationship=relationship,
            matrix_key=matrix_key,
            reason="unknown_relationship_type",
        )

    status = EDGE_COMPATIBILITY.get(
        (source_supertype, canonical_relationship, target_supertype), "suspect"
    )
    return EdgeCompatibilityVerdict(
        status=status,
        source_supertype=source_supertype,
        target_supertype=target_supertype,
        relationship=canonical_relationship,
        matrix_key=f"{source_supertype}.{canonical_relationship}.{target_supertype}",
        reason="matrix_match" if status != "suspect" else "matrix_missing",
    )


def _coerce_entity_type(value: str | EntityType) -> EntityType:
    if isinstance(value, EntityType):
        return value
    return EntityType.from_string(value)
