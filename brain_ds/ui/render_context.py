from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from pathlib import Path

from brain_ds.ontology import Graph
import networkx as nx

from .theme import color_for_type


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


def build_render_context(graph: Graph, workspace: WorkspaceContext | None = None, *, graph_id: str | None = None) -> dict:
    adjacency: dict[str, set[str]] = defaultdict(set)
    incident_edges: dict[str, list] = defaultdict(list)
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

    nodes = []
    for node in graph.nodes:
        if not node.id:
            continue
        node_type = node.type.value
        nodes.append(
            {
                "id": node.id,
                "label": node.label or node.id,
                "type": node_type,
                "supertype": node.supertype or node.type.supertype,
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
        )

    edges = []
    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        incident_edges[edge.source].append(edge)
        if edge.target != edge.source:
            incident_edges[edge.target].append(edge)
        edges.append(
            {
                "from": edge.source,
                "to": edge.target,
                "label": edge.label.value,
                "title": _edge_title(edge.label.value, edge.reasons),
                "width": 1.0 + ((edge.weight or 0.0) * 4.0),
                "score": float(edge.weight or 0.0),
            }
        )

    type_buckets: dict[str, dict[str, dict]] = defaultdict(dict)
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

    type_groups = [
        {
            "supertype": supertype,
            "types": sorted(payload.values(), key=lambda entry: entry["type"].lower()),
        }
        for supertype, payload in sorted(type_buckets.items(), key=lambda kv: kv[0].lower())
    ]

    detail_index, evidence_records = _build_detail_index(graph)

    for node in nodes:
        node_id = node["id"]
        node["score"] = _compute_node_score(node_id, incident_edges)
        node["updated_at"] = _compute_node_updated_at(node_evidence_ids.get(node_id, []), evidence_records_map, generated_at)
        node["neighbor_count"] = _compute_neighbor_count(node_id, adjacency)

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
    }


def _compute_node_score(node_id: str, incident_edges: dict[str, list]) -> float:
    node_incident_edges = incident_edges.get(node_id, [])
    if not node_incident_edges:
        return 0.0
    return max(float(edge.weight or 0.0) for edge in node_incident_edges)


def _compute_neighbor_count(node_id: str, adjacency: dict[str, set[str]]) -> int:
    return len(adjacency.get(node_id, set()))


def _compute_node_updated_at(evidence_ids: list[str], evidence_records: dict[str, dict], fallback: str) -> str:
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


def _edge_title(label: str, reasons: list[str] | None) -> str:
    reasons_text = "; ".join(reasons or [])
    if reasons_text:
        return f"{label} — {reasons_text}"
    return label


def _node_title(details: dict, card_sections: list | None) -> str:
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


def _build_detail_index(graph: Graph) -> tuple[dict[str, dict], dict[str, dict]]:
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
    incoming_by_target: dict[str, list[dict]] = defaultdict(list)
    outgoing_by_source: dict[str, list[dict]] = defaultdict(list)

    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        relation = {
            "edge_label": edge.label.value,
            "source_id": edge.source,
            "source_label": node_lookup.get(edge.source).label if node_lookup.get(edge.source) else edge.source,
            "target_id": edge.target,
            "target_label": node_lookup.get(edge.target).label if node_lookup.get(edge.target) else edge.target,
            "reasons": edge.reasons or [],
            "evidence_ids": edge.evidence_ids or [],
        }
        outgoing_by_source[edge.source].append(relation)
        incoming_by_target[edge.target].append(relation)

    detail_index: dict[str, dict] = {}
    for node in graph.nodes:
        if not node.id:
            continue

        detail_index[node.id] = {
            "node": {
                "id": node.id,
                "label": node.label or node.id,
                "type": node.type.value,
                "supertype": node.supertype or node.type.supertype,
                "color": {
                    "background": color_for_type(node.type.value, "dark"),
                    "dark": color_for_type(node.type.value, "dark"),
                    "light": color_for_type(node.type.value, "light"),
                },
            },
            "sections": _node_sections(node.details or {}, node.card_sections, node.type),
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

    return detail_index, evidence_records


def _node_sections(details: dict, card_sections: list | None, entity_type) -> list[dict]:
    if card_sections is not None:
        expected = [title.strip().lower() for title in (entity_type.expected_sections or [])]
        present = {section.title.strip().lower(): section for section in (card_sections or [])}
        sections = []
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
    sections = []
    for title, key, order in fallback_fields:
        value = details.get(key)
        if value:
            sections.append(
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
    return sections


def _compute_components(graph: Graph) -> dict[str, int]:
    network = nx.Graph()
    network.add_nodes_from(node.id for node in graph.nodes if node.id)
    network.add_edges_from((edge.source, edge.target) for edge in graph.edges if edge.source and edge.target)
    components = sorted(nx.connected_components(network), key=lambda component: (-len(component), min(component)))
    return {node_id: index for index, component in enumerate(components) for node_id in component}
