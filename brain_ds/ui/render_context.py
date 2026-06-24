from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Any

from brain_ds.ontology import EntityType, Graph, RelationshipType
import networkx as nx

from .theme import color_for_type

# Avoid a hard import cycle: GraphStore lives in brain_ds.store, which does not
# import brain_ds.ui.  We accept the store as Any and duck-type the call.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain_ds.store.graph_store import GraphStore


CONTRACT_VERSION = "1.0.0"


@dataclass(frozen=True)
class WorkspaceContext:
    project_root: Path
    display_path: str
    store_path: Path

    @classmethod
    def from_root_and_graph(cls, project_root: Path, graph_path: Path) -> "WorkspaceContext":
        root = project_root.resolve()
        graph = graph_path.resolve()
        try:
            rel = graph.relative_to(root)
            display_path = rel.as_posix()
        except ValueError:
            display_path = graph.as_posix()
        return cls(
            project_root=root,
            display_path=display_path,
            store_path=root / ".brain_ds" / "store.db",
        )

    @property
    def root(self) -> str:
        return str(self.project_root)

    @property
    def graph_path(self) -> str:
        display = Path(self.display_path)
        if display.is_absolute():
            return str(display)
        return str((self.project_root / display).resolve())


_workspace_fallback_warned = False


def build_render_context(
    graph: Graph,
    workspace: WorkspaceContext | None = None,
    *,
    graph_id: str | None = None,
    store: "GraphStore | None" = None,
) -> dict:
    adjacency: dict[str, set[str]] = defaultdict(set)
    incident_edges: dict[str, list[Any]] = defaultdict(list)
    component_ids = _compute_components(graph)
    evidence_records_map = {
        item.id: {
            "id": item.id,
            "type": item.type,
            "source": item.source,
            "content": item.content,
            "provenance": item.provenance,
            "timestamp": item.timestamp,
        }
        for item in graph.evidence
        if item.id
    }
    generated_at = graph.generated_at or ""
    workspace_meta = _compute_workspace_meta(workspace)
    node_evidence_ids = {node.id: (node.evidence_ids or []) for node in graph.nodes if node.id}

    nodes: list[dict[str, Any]] = []
    for node in graph.nodes:
        if not node.id:
            continue
        entity_type = _entity_type(node.type)
        node_type = entity_type.value
        node_payload: dict[str, Any] = {
            "id": node.id,
            "label": node.label or node.id,
            "type": node_type,
            "supertype": node.supertype or entity_type.supertype,
            "color": {
                "background": color_for_type(node_type, "dark"),
                "dark": color_for_type(node_type, "dark"),
                "light": color_for_type(node_type, "light"),
            },
            "title": _node_title(node.details or {}, node.card_sections),
            "parent_id": node.parent_id,
            "depth": node.depth,
            "component_id": component_ids.get(node.id),
        }
        # C1 fix: project layout_hint x/y so the renderer cold-start gate has a
        # real signal. Only include BOTH keys when both are present — a partial
        # hint (x only or y only) carries no useful positional information for
        # the all-nodes-positioned gate in renderer.ts.
        if node.layout_hint:
            lx = node.layout_hint.get("x")
            ly = node.layout_hint.get("y")
            if lx is not None and ly is not None:
                node_payload["x"] = lx
                node_payload["y"] = ly
        nodes.append(node_payload)

    edges: list[dict[str, Any]] = []
    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        relationship_type = _relationship_type(edge.label)
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        incident_edges[edge.source].append(edge)
        if edge.target != edge.source:
            incident_edges[edge.target].append(edge)
        edges.append(
            {
                "from": edge.source,
                "to": edge.target,
                "label": relationship_type.value,
                "title": _edge_title(relationship_type.value, edge.reasons),
                "width": 1.0 + ((edge.weight or 0.0) * 4.0),
                "score": float(edge.weight or 0.0),
            }
        )

    type_buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in nodes:
        supertype = item["supertype"]
        node_type = item["type"]
        if node_type not in type_buckets[supertype]:
            type_buckets[supertype][node_type] = {
                "type": node_type,
                "color": item["color"],
                "count": 0,
            }
        type_buckets[supertype][node_type]["count"] += 1

    type_groups = []
    for supertype, payload in sorted(type_buckets.items(), key=lambda kv: kv[0].lower()):
        type_groups.append(
            {
                "supertype": supertype,
                "types": sorted(list(payload.values()), key=_type_bucket_sort_key),
            }
        )

    detail_index, evidence_records = _build_detail_index(graph)

    for node_payload in nodes:
        node_id = str(node_payload["id"])
        node_payload["score"] = _compute_node_score(node_id, incident_edges)
        node_payload["updated_at"] = _compute_node_updated_at(node_evidence_ids.get(node_id, []), evidence_records_map, generated_at)
        node_payload["neighbor_count"] = _compute_neighbor_count(node_id, adjacency)

    pending = _build_pending_confirmations(store, graph_id)

    return {
        "contract_version": CONTRACT_VERSION,
        "meta": {
            "org": graph.org or "Organization",
            "graph_id": graph_id or "",
            "generated_at": graph.generated_at or "",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "workspace": workspace_meta,
        },
        "nodes": nodes,
        "edges": edges,
        "type_groups": type_groups,
        "adjacency": {node_id: sorted(neighbors) for node_id, neighbors in sorted(adjacency.items())},
        "detail_index": detail_index,
        "evidence_records": evidence_records,
        "ui_defaults": {
            "hierarchical": True,
            "physics": False,
        },
        "pending_confirmations": pending,
    }


def _compute_node_score(node_id: str, incident_edges: dict[str, list[Any]]) -> float:
    node_incident_edges = incident_edges.get(node_id, [])
    if not node_incident_edges:
        return 0.0
    return max(float(edge.weight or 0.0) for edge in node_incident_edges)


def _compute_neighbor_count(node_id: str, adjacency: dict[str, set[str]]) -> int:
    return len(adjacency.get(node_id, set()))


def _compute_node_updated_at(evidence_ids: list[str], evidence_records: dict[str, dict[str, Any]], fallback: str) -> str:
    incident_timestamps = [
        evidence_records[evidence_id]["timestamp"]
        for evidence_id in evidence_ids
        if evidence_id in evidence_records and evidence_records[evidence_id].get("timestamp")
    ]
    if not incident_timestamps:
        return fallback
    return max(incident_timestamps)


def _compute_workspace_meta(workspace: WorkspaceContext | None) -> dict:
    global _workspace_fallback_warned

    if workspace is None:
        if not _workspace_fallback_warned:
            logging.warning(
                "build_render_context: no WorkspaceContext supplied; synthesizing project='default' fallback."
            )
            _workspace_fallback_warned = True
        return {
            "root": "",
            "displayPath": "",
            "project": "default",
            "graph": "(unknown)",
        }

    root = workspace.project_root.resolve()
    display_path = workspace.display_path

    parts = display_path.split("/") if display_path else []
    if len(parts) >= 2:
        project = parts[0]
    else:
        project = root.name or "default"

    return {
        "root": str(root),
        "displayPath": display_path,
        "project": project,
        "graph": Path(display_path).stem or "(unknown)",
    }


def _build_pending_confirmations(store: Any, graph_id: str | None) -> dict:
    """Return pending-confirmation summary for the render context.

    Returns ``{"count": int, "items": list[dict]}`` always.
    - When *store* is None or *graph_id* is None/empty, returns count=0 and
      empty items (backwards-compatible with callers that pass no store).
    - Each item exposes the fields most useful for UI surfacing; other fields
      from LedgerRow are omitted to keep the payload compact.
    """
    if store is None or not graph_id:
        return {"count": 0, "items": []}

    try:
        rows = store.list_pending_confirmations(graph_id)
    except Exception:
        # Graph not found or store error — degrade gracefully; never crash the renderer
        return {"count": 0, "items": []}

    items = [
        {
            "id": row.id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "status": row.status,
            "fact_label": row.fact_label,
            "fact_path": row.fact_path,
            "fact_value": row.fact_value,
            "fact_subject_type": row.fact_subject_type,
            "initial_confidence": row.initial_confidence,
            "current_confidence": row.current_confidence,
            "flagged_reason": row.flagged_reason,
            "captured_at": row.captured_at,
        }
        for row in rows
    ]
    return {"count": len(items), "items": items}


def _edge_title(label: str, reasons: list[str] | None) -> str:
    reasons_text = "; ".join(reasons or [])
    if reasons_text:
        return f"{label} — {reasons_text}"
    return label


def _node_title(details: dict[str, Any], card_sections: list[Any] | None) -> str:
    if card_sections:
        parts = [
            f"<b>{section.title}</b>: {section.content}"
            for section in sorted(card_sections, key=lambda item: item.order)
        ]
        return "<br>".join(parts)
    return (
        f"<b>What</b>: {details.get('what', '')}<br>"
        f"<b>Why</b>: {details.get('why', '')}<br>"
        f"<b>Where</b>: {details.get('where', '')}<br>"
        f"<b>Learned</b>: {details.get('learned', '')}"
    )


def _build_detail_index(graph: Graph) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    evidence_records = {
        item.id: {
            "id": item.id,
            "type": item.type,
            "source": item.source,
            "content": item.content,
            "provenance": item.provenance,
            "timestamp": item.timestamp,
        }
        for item in graph.evidence
        if item.id
    }

    node_lookup = {node.id: node for node in graph.nodes if node.id}
    incoming_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        relationship_type = _relationship_type(edge.label)
        source_node = node_lookup.get(edge.source)
        target_node = node_lookup.get(edge.target)
        relation = {
            "edge_label": relationship_type.value,
            "source_id": edge.source,
            "source_label": source_node.label if source_node else edge.source,
            "target_id": edge.target,
            "target_label": target_node.label if target_node else edge.target,
            "reasons": edge.reasons or [],
            "evidence_ids": edge.evidence_ids or [],
        }
        outgoing_by_source[edge.source].append(relation)
        incoming_by_target[edge.target].append(relation)

    # Build a lookup of child nodes grouped by parent_id for digest aggregation
    children_by_parent: dict[str, list[Any]] = defaultdict(list)
    for node in graph.nodes:
        if node.id and node.parent_id:
            children_by_parent[node.parent_id].append(node)

    internal_subtrees_by_source = _build_internal_subtrees(graph.nodes, children_by_parent)

    detail_index: dict[str, dict[str, Any]] = {}
    for node in graph.nodes:
        if not node.id:
            continue
        entity_type = _entity_type(node.type)

        entry: dict[str, Any] = {
            "node": {
                "id": node.id,
                "label": node.label or node.id,
                "type": entity_type.value,
                "supertype": node.supertype or entity_type.supertype,
                "color": {
                    "background": color_for_type(entity_type.value, "dark"),
                    "dark": color_for_type(entity_type.value, "dark"),
                    "light": color_for_type(entity_type.value, "light"),
                },
                "connection": (node.details or {}).get("connection") if entity_type.value == "Data Source" else None,
            },
            "sections": _node_sections(node.details or {}, node.card_sections, entity_type),
            # Free-form per-node notes stored in details.notes (string).
            # Exposed here so the reader can render and edit it without a
            # round-trip — the PATCH /api/nodes endpoint merges details fields.
            "notes": (node.details or {}).get("notes", "") if node.details else "",
            "evidence": [
                evidence_records[evidence_id]
                for evidence_id in (node.evidence_ids or [])
                if evidence_id in evidence_records
            ],
            "relationships": {
                "incoming": sorted(incoming_by_target.get(node.id, []), key=lambda item: item["source_label"].lower()),
                "outgoing": sorted(outgoing_by_source.get(node.id, []), key=lambda item: item["target_label"].lower()),
            },
            "editable_fields": node.editable_fields or [],
        }

        # DDS-1/DDS-2: aggregate child table nodes into a documentation digest
        # for Data Source nodes only. Child nodes are identified by parent_id.
        if entity_type.value == "Data Source":
            entry["documentation_digest"] = _build_documentation_digest(
                node.id, children_by_parent, outgoing_by_source
            )
            entry["internal_subtree"] = internal_subtrees_by_source.get(node.id, [])

        detail_index[node.id] = entry

    return detail_index, evidence_records


def _node_sections(details: dict[str, Any], card_sections: list[Any] | None, entity_type: EntityType) -> list[dict[str, Any]]:
    if card_sections is not None:
        expected = [title.strip().lower() for title in (entity_type.expected_sections or [])]
        present = {section.title.strip().lower(): section for section in (card_sections or [])}
        sections: list[dict[str, Any]] = []
        for section in sorted(card_sections, key=lambda item: item.order):
            if not section.content:
                continue
            sections.append(
                {
                    "title": section.title,
                    "content": section.content,
                    "icon": section.icon,
                    "order": section.order,
                    "accent_color": None,
                    "origin": "card_sections",
                    "is_gap": False,
                }
            )

        order = len(sections) + 1
        for expected_title in entity_type.expected_sections or []:
            key = expected_title.strip().lower()
            section = present.get(key)
            if not section or not section.content:
                sections.append(
                    {
                        "title": expected_title,
                        "content": "",
                        "icon": "",
                        "order": order,
                        "accent_color": None,
                        "origin": "expected_gap",
                        "is_gap": True,
                    }
                )
            order += 1

        for section in sorted(card_sections, key=lambda item: item.order):
            key = section.title.strip().lower()
            if key in expected or not section.content:
                continue
            sections.append(
                {
                    "title": section.title,
                    "content": section.content,
                    "icon": section.icon,
                    "order": section.order,
                    "accent_color": None,
                    "origin": "card_sections",
                    "is_gap": False,
                }
            )
        return sections

    fallback_fields = (
        ("What", "what", 1),
        ("Why", "why", 2),
        ("Where", "where", 3),
        ("Learned", "learned", 4),
    )
    fallback_sections: list[dict[str, Any]] = []
    for title, key, order in fallback_fields:
        value = details.get(key)
        if value:
            fallback_sections.append(
                {
                    "title": title,
                    "content": value,
                    "icon": "",
                    "order": order,
                    "accent_color": None,
                    "origin": "details_fallback",
                    "is_gap": False,
                }
            )
    return fallback_sections


def _build_documentation_digest(
    source_id: str,
    children_by_parent: dict[str, list[Any]],
    outgoing_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """DDS-1/DDS-2: Build a documentation digest for a Data Source node.

    Aggregates child table-level nodes' card_sections to expose per-table
    columns/fields markdown, relationships, risks, and schema_baseline status
    in a single payload — enabling one-call agent answerability (DDS-5).
    """
    child_nodes = [
        child
        for child in children_by_parent.get(source_id, [])
        if _entity_type(child.type).supertype != "data-internal"
    ]

    tables: list[dict[str, Any]] = []
    for child in sorted(child_nodes, key=lambda n: (n.label or n.id or "").lower()):
        sections = child.card_sections or []
        columns_markdown = ""
        section_list: list[dict[str, Any]] = []
        for section in sorted(sections, key=lambda s: s.order):
            section_list.append(
                {
                    "title": section.title,
                    "content": section.content,
                }
            )
            if section.title.strip().lower() in ("columns / fields", "columns/fields", "columns", "fields"):
                columns_markdown = section.content or ""

        child_details = child.details or {}
        tables.append(
            {
                "node_id": child.id,
                "label": child.label or child.id or "",
                "sections": section_list,
                "columns_markdown": columns_markdown,
                "purpose": child_details.get("what", ""),
                "owner": child_details.get("where", ""),
                "refresh": child_details.get("learned", ""),
                "schema_baseline_status": (
                    "baseline-present"
                    if isinstance(child_details.get("schema_baseline"), dict)
                    else "no-baseline"
                ),
            }
        )

    # Collect outgoing relationships from the source node for the digest
    relationships = [
        {
            "edge_label": rel["edge_label"],
            "target_id": rel["target_id"],
            "target_label": rel["target_label"],
        }
        for rel in outgoing_by_source.get(source_id, [])
    ]

    return {
        "tables": tables,
        "relationships": relationships,
    }


def _build_internal_subtrees(nodes: list[Any], children_by_parent: dict[str, list[Any]]) -> dict[str, list[dict[str, Any]]]:
    node_lookup = {node.id: node for node in nodes if node.id}
    source_ids = [node.id for node in nodes if node.id and _entity_type(node.type) == EntityType.DATA_SOURCE]
    explicit_by_source = {source_id: _explicit_internal_subtree(source_id, node_lookup) for source_id in source_ids}
    return {
        source_id: subtree if subtree else _derive_internal_subtree(source_id, children_by_parent)
        for source_id, subtree in explicit_by_source.items()
    }


def _explicit_internal_subtree(source_id: str, node_lookup: dict[str, Any]) -> list[dict[str, Any]]:
    internal_nodes = [
        node
        for node in node_lookup.values()
        if _entity_type(node.type).supertype == "data-internal"
        and _descends_from_source(node.id, source_id, node_lookup)
    ]
    children_by_parent: dict[str, list[Any]] = defaultdict(list)
    for node in internal_nodes:
        children_by_parent[node.parent_id].append(node)
    for children in children_by_parent.values():
        children.sort(key=lambda item: (item.depth, (item.label or item.id or "").lower(), item.id or ""))

    def build(node: Any) -> dict[str, Any]:
        item = _internal_node_payload(node)
        item["children"] = [build(child) for child in children_by_parent.get(node.id, [])]
        return item

    return [build(node) for node in children_by_parent.get(source_id, [])]


def _derive_internal_subtree(source_id: str, children_by_parent: dict[str, list[Any]]) -> list[dict[str, Any]]:
    subtree: list[dict[str, Any]] = []
    legacy_children = [
        child
        for child in children_by_parent.get(source_id, [])
        if _entity_type(child.type).supertype != "data-internal"
    ]
    for child in sorted(legacy_children, key=lambda item: ((item.label or item.id or "").lower(), item.id or "")):
        table_label = child.label or child.id or "table"
        table_id = f"{source_id}-table-{_slugify(table_label)}"
        table_item = {
            "id": table_id,
            "label": table_label,
            "type": EntityType.DATA_CONTAINER.value,
            "details": {"kind": "table", "source_node_id": child.id},
            "supertype": EntityType.DATA_CONTAINER.supertype,
            "parent_id": source_id,
            "depth": 1,
            "children": [],
            "ephemeral": True,
        }
        for column_name, data_type in _extract_columns_from_sections(child.card_sections or []):
            table_item["children"].append(
                {
                    "id": f"{table_id}-column-{_slugify(column_name)}",
                    "label": column_name,
                    "type": EntityType.DATA_FIELD.value,
                    "details": {"kind": "column", "data_type": data_type, "source_node_id": child.id},
                    "supertype": EntityType.DATA_FIELD.supertype,
                    "parent_id": table_id,
                    "depth": 2,
                    "children": [],
                    "ephemeral": True,
                }
            )
        subtree.append(table_item)
    return subtree


def _descends_from_source(node_id: str | None, source_id: str, node_lookup: dict[str, Any]) -> bool:
    current_id = node_id
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            return False
        visited.add(current_id)
        if current_id == source_id:
            return True
        node = node_lookup.get(current_id)
        if node is None:
            return False
        current_id = node.parent_id
    return False


def _internal_node_payload(node: Any) -> dict[str, Any]:
    entity_type = _entity_type(node.type)
    return {
        "id": node.id,
        "label": node.label or node.id,
        "type": entity_type.value,
        "details": node.details or {},
        "supertype": node.supertype or entity_type.supertype,
        "parent_id": node.parent_id,
        "depth": node.depth,
    }


def _extract_columns_from_sections(card_sections: list[Any]) -> list[tuple[str, str]]:
    columns: list[tuple[str, str]] = []
    for section in card_sections:
        if section.title.strip().lower() not in ("columns / fields", "columns/fields", "columns", "fields"):
            continue
        columns.extend(_extract_markdown_table_columns(section.content or ""))
    return columns


def _extract_markdown_table_columns(markdown: str) -> list[tuple[str, str]]:
    columns: list[tuple[str, str]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0].lower() in {"col", "column", "field", "name"}:
            continue
        columns.append((cells[0], cells[1] if len(cells) > 1 else ""))
    return columns


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def _compute_components(graph: Graph) -> dict[str, int]:
    network = nx.Graph()
    network.add_nodes_from(node.id for node in graph.nodes if node.id)
    network.add_edges_from((edge.source, edge.target) for edge in graph.edges if edge.source and edge.target)
    components = sorted(nx.connected_components(network), key=lambda component: (-len(component), min(component)))
    return {node_id: index for index, component in enumerate(components) for node_id in component}


def _entity_type(value: EntityType | str) -> EntityType:
    return value if isinstance(value, EntityType) else EntityType.from_string(value)


def _relationship_type(value: RelationshipType | str) -> RelationshipType:
    return value if isinstance(value, RelationshipType) else RelationshipType.from_string(value)


def _type_bucket_sort_key(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("type", "")).lower()
    return str(entry).lower()
