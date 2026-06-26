"""Semantic cluster governance helpers."""

from __future__ import annotations

from brain_ds.store.models import ClusterMetadataV1, NodeRow


def choose_cluster_center(nodes: list[NodeRow]) -> dict:
    """Select the governed center for a candidate cluster.

    KPI and Business Problem anchors are semantic truth. Department is only the
    fallback/home when no semantic anchor is present.
    """
    kpi = next((node for node in nodes if node.type == "KPI"), None)
    problem = next((node for node in nodes if node.type == "Problem / Improvement Area"), None)
    department = next((node for node in nodes if node.type == "Department"), None)
    source_ids = [node.id for node in nodes if node.type == "Data Source"]
    role_ids = [node.id for node in nodes if node.type == "Role"]

    primary = kpi or problem or department
    if primary is None:
        raise ValueError("Cluster candidates require a KPI, Business Problem, or Department anchor")

    is_semantic_anchor = primary is kpi or primary is problem
    quality_signals = {
        "center_selection": "semantic_anchor" if is_semantic_anchor else "department_fallback"
    }
    if primary is department:
        quality_signals["missing_anchor_gap"] = "kpi_or_business_problem"

    metadata = ClusterMetadataV1(
        status="proposed",
        primary_anchor_id=primary.id,
        primary_anchor_type=primary.type,
        dominant_department_id=department.id if department is not None else None,
        supporting_anchor_ids=[*source_ids, *role_ids],
        needs_source=not bool(source_ids),
        source_requirements={} if source_ids else {"missing": "primary_data_source"},
        quality_signals=quality_signals,
    )
    return metadata.to_dict()
