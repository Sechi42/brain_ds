"""Pure KPI dossier assembly use case."""

from __future__ import annotations

from typing import Any

from brain_ds.dossier.models import (
    ActorFacet,
    DataContainerFacet,
    DataSourceFacet,
    DossierGapInputs,
    DossierGraphView,
    KpiDossier,
    LimitationsFacet,
    ProcessFacet,
)
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.retrieval.neighborhood import expand_neighborhood

_ACTOR_TYPES = {"Organization", "Department", "Role"}
_PROCESS_TYPES = {"Heuristic", "Project", "Decision"}
_SUPPORTED_SUPERTYPES = {"metric", "data", "data-internal", "actor", "process"}


def assemble_kpi_dossier(
    view: DossierGraphView,
    gaps: DossierGapInputs,
    *,
    kpi_node_id: str,
    depth: int = 2,
) -> KpiDossier:
    kpi = view.nodes_by_id[kpi_node_id]
    depth_by_node = expand_neighborhood([kpi_node_id], view.adjacency, depth=depth)
    reachable = {
        node_id
        for node_id, node_depth in depth_by_node.items()
        if node_depth <= depth and _supertype(view.nodes_by_id.get(node_id)) in _SUPPORTED_SUPERTYPES
    }

    measured_from_label = RelationshipType.MEASURED_FROM.value
    confirmed_containers = _targets_for_label(view, kpi_node_id, measured_from_label, type_name="DataContainer")
    confirmed_fields = _targets_for_label(view, kpi_node_id, measured_from_label, type_name="DataField")

    data_source_ids = {
        node_id
        for node_id in reachable
        if _type(view.nodes_by_id.get(node_id)) == "DataSource"
    }
    for container_id in confirmed_containers | confirmed_fields:
        source_id = _data_source_ancestor(view, container_id)
        if source_id is not None:
            data_source_ids.add(source_id)

    data_sources = [_build_data_source(view, ds_id, confirmed_containers, confirmed_fields) for ds_id in sorted(data_source_ids)]
    actors = [ActorFacet(view.nodes_by_id[node_id]) for node_id in sorted(reachable) if _type(view.nodes_by_id[node_id]) in _ACTOR_TYPES]
    processes = [ProcessFacet(view.nodes_by_id[node_id]) for node_id in sorted(reachable) if _type(view.nodes_by_id[node_id]) in _PROCESS_TYPES]

    unconfirmed_lineage = _dedupe_dicts(
        [
            *gaps.unconfirmed_lineage,
            *_unconfirmed_lineage_from_edges(view, kpi_node_id, measured_from_label),
            *_hierarchy_unconfirmed_lineage(view, kpi_node_id, data_source_ids, confirmed_containers),
        ]
    )
    unmapped_sources = [
        {"gap_type": "unmapped_source", "description": f"Data Source {facet.node.label} has no mapped containers", "source": "inferred"}
        for facet in data_sources
        if not facet.containers
    ]
    if not data_sources:
        unmapped_sources.append(
            {"gap_type": "unmapped_source", "description": f"KPI {kpi.label} has no mapped data sources", "source": "inferred"}
        )

    limitations = LimitationsFacet(
        unmapped_sources=unmapped_sources,
        unconfirmed_lineage=unconfirmed_lineage,
        missing_ownership=not _has_any_label(view.edges, kpi_node_id, {RelationshipType.ACCOUNTABLE.value, RelationshipType.OWNED_BY.value}),
        missing_process=not _has_process_edge(view, kpi_node_id),
        completeness=_dedupe_dicts(gaps.completeness),
        currency=_dedupe_dicts(gaps.currency),
        weak_edges=_dedupe_dicts(gaps.weak_edges),
    )
    summary = f"KPI {kpi.label} dossier assembled with {len(data_sources)} data source(s)."
    return KpiDossier(kpi=kpi, data_sources=data_sources, actors=actors, processes=processes, limitations=limitations, summary=summary)


def _build_data_source(
    view: DossierGraphView,
    source_id: str,
    confirmed_containers: set[str],
    confirmed_fields: set[str],
) -> DataSourceFacet:
    source = view.nodes_by_id[source_id]
    container_ids = {container_id for container_id in confirmed_containers if _data_source_ancestor(view, container_id) == source_id}
    containers = [
        _build_container(view, container_id, confirmed_fields, "confirmed-edge")
        for container_id in sorted(container_ids)
    ]
    return DataSourceFacet(node=source, containers=containers, lineage_source="confirmed-edge" if containers else "unconfirmed")


def _build_container(
    view: DossierGraphView,
    container_id: str,
    confirmed_fields: set[str],
    lineage_source: str,
) -> DataContainerFacet:
    fields = [view.nodes_by_id[field_id] for field_id in sorted(confirmed_fields) if _parent_id(view.nodes_by_id.get(field_id)) == container_id]
    return DataContainerFacet(node=view.nodes_by_id[container_id], fields=fields, lineage_source=lineage_source)


def _targets_for_label(view: DossierGraphView, source: str, label: str, *, type_name: str) -> set[str]:
    targets: set[str] = set()
    for edge in view.edges:
        target_id = getattr(edge, "target", "")
        target = view.nodes_by_id.get(target_id)
        if (
            getattr(edge, "source", None) == source
            and getattr(edge, "label", None) == label
            and _type(target) == type_name
            and _ledger_status(view, edge) == "confirmed"
        ):
            targets.add(target_id)
    return targets


def _unconfirmed_lineage_from_edges(view: DossierGraphView, source: str, label: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for edge in view.edges:
        target_id = getattr(edge, "target", "")
        target = view.nodes_by_id.get(target_id)
        if getattr(edge, "source", None) != source or getattr(edge, "label", None) != label:
            continue
        if _type(target) not in {"DataContainer", "DataField"} or _ledger_status(view, edge) == "confirmed":
            continue
        edge_id = str(getattr(edge, "edge_id", f"{source}->{target_id}:{label}"))
        items.append(
            {
                "candidate_id": edge_id,
                "from_node": source,
                "to_node": target_id,
                "relationship": label,
                "source": "confidence_ledger",
            }
        )
    return items


def _ledger_status(view: DossierGraphView, edge: Any) -> str | None:
    edge_id = getattr(edge, "edge_id", None)
    return view.ledger_status_by_target.get(edge_id) if isinstance(edge_id, str) else None


def _hierarchy_unconfirmed_lineage(
    view: DossierGraphView,
    kpi_node_id: str,
    data_source_ids: set[str],
    confirmed_containers: set[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source_id in sorted(data_source_ids):
        for container in view.children_by_parent.get(source_id, []):
            if _type(container) != "DataContainer" or container.id in confirmed_containers:
                continue
            items.append(
                {
                    "candidate_id": f"{kpi_node_id}->{container.id}:measured-from",
                    "from_node": kpi_node_id,
                    "to_node": container.id,
                    "relationship": RelationshipType.MEASURED_FROM.value,
                    "source": "hierarchy-inferred",
                }
            )
    return items


def _data_source_ancestor(view: DossierGraphView, node_id: str) -> str | None:
    current_id: str | None = node_id
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        current = view.nodes_by_id.get(current_id)
        if current is None:
            return None
        if _type(current) == "DataSource":
            return current.id
        current_id = _parent_id(current)
    return None


def _has_any_label(edges: list[Any], source: str, labels: set[str]) -> bool:
    return any(getattr(edge, "source", None) == source and getattr(edge, "label", None) in labels for edge in edges)


def _has_process_edge(view: DossierGraphView, source: str) -> bool:
    for edge in view.edges:
        if getattr(edge, "source", None) != source or getattr(edge, "label", None) != RelationshipType.DEPENDS_ON.value:
            continue
        target = view.nodes_by_id.get(getattr(edge, "target", ""))
        if _type(target) in _PROCESS_TYPES:
            return True
    return False


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _type(node: Any) -> str | None:
    value = getattr(node, "type", None) if node is not None else None
    return value.replace(" ", "") if isinstance(value, str) else value


def _supertype(node: Any) -> str | None:
    return getattr(node, "supertype", None) if node is not None else None


def _parent_id(node: Any) -> str | None:
    return getattr(node, "parent_id", None) if node is not None else None
