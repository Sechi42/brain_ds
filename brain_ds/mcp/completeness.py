"""Graph completeness assessment — the pre-mapping gate.

Pure logic behind the `assess_completeness` MCP tool: given the nodes of a
graph, report which entity types are missing or underspecified so mapping and
BRD agents can stop and recommend elicitation instead of wiring edges between
hollow nodes.
"""

from __future__ import annotations

from typing import Any

from brain_ds.ontology.entity_types import EntityType
from brain_ds.scoring.similarity import is_sparse
from brain_ds.store.models import NodeRow

STATUS_MISSING = "missing"
STATUS_SPARSE = "sparse"
STATUS_PRESENT = "present"

# 3+ empty entity types means the graph is hollow: elicit before mapping.
ELICIT_MISSING_THRESHOLD = 3

RECOMMEND_ELICIT = "elicit"
RECOMMEND_DOCUMENT = "document"
RECOMMEND_PROCEED = "proceed_with_gaps"

# BRD-relevant types, in dataset fingerprint order (mirrors
# COMPLETENESS_MATRIX_TEMPLATE["dataset_fingerprint_order"] plus Organization).
ASSESSED_TYPES: tuple[str, ...] = tuple(
    e.value for e in EntityType if e is not EntityType.UNKNOWN
)


def assess_graph_completeness(nodes: list[NodeRow]) -> dict[str, Any]:
    by_type: dict[str, list[NodeRow]] = {value: [] for value in ASSESSED_TYPES}
    for node in nodes:
        entity = EntityType.from_string(node.type)
        if entity is EntityType.UNKNOWN:
            continue
        by_type[entity.value].append(node)

    matrix: dict[str, str] = {}
    missing: list[str] = []
    underspecified: list[str] = []
    for type_value in ASSESSED_TYPES:
        members = by_type[type_value]
        if not members:
            matrix[type_value] = STATUS_MISSING
            missing.append(type_value)
            continue
        sparse_members = [node for node in members if is_sparse(node)]
        underspecified.extend(node.id for node in sparse_members)
        matrix[type_value] = STATUS_SPARSE if sparse_members else STATUS_PRESENT

    if len(missing) >= ELICIT_MISSING_THRESHOLD:
        recommendation = RECOMMEND_ELICIT
    elif underspecified:
        recommendation = RECOMMEND_DOCUMENT
    else:
        recommendation = RECOMMEND_PROCEED

    return {
        "completeness_matrix": matrix,
        "missing_for_brd": missing,
        "underspecified_nodes": sorted(underspecified),
        "missing_count": len(missing),
        "pre_mapping_recommendation": recommendation,
        "recommendation_detail": {
            RECOMMEND_ELICIT: (
                f"{len(missing)} entity types have zero nodes — run elicit-context "
                "before mapping; edges between hollow nodes produce a hollow BRD."
            ),
            RECOMMEND_DOCUMENT: (
                f"{len(set(underspecified))} node(s) are underspecified (empty 'where' "
                "or learned starts with 'Underspecified') — document them before "
                "they can receive automatic edges."
            ),
            RECOMMEND_PROCEED: "All assessed entity types have grounded nodes.",
        }[recommendation],
    }
