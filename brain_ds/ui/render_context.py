from __future__ import annotations

from collections import defaultdict

from brain_ds.ontology import Graph

from .theme import color_for_type


def build_render_context(graph: Graph) -> dict:
    adjacency: dict[str, set[str]] = defaultdict(set)
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
                "color": color_for_type(node_type),
                "title": _node_title(node.details or {}, node.card_sections),
            }
        )

    edges = []
    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        edges.append(
            {
                "from": edge.source,
                "to": edge.target,
                "label": edge.label.value,
                "title": _edge_title(edge.label.value, edge.reasons),
                "width": 1.0 + ((edge.weight or 0.0) * 4.0),
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

    return {
        "meta": {
            "org": graph.org or "Organization",
            "generated_at": graph.generated_at or "",
            "node_count": len(nodes),
            "edge_count": len(edges),
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
                "color": color_for_type(node.type.value),
            },
            "sections": _node_sections(node.details or {}, node.card_sections),
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


def _node_sections(details: dict, card_sections: list | None) -> list[dict]:
    if card_sections is not None:
        return [
            {
                "title": section.title,
                "content": section.content,
                "icon": section.icon,
                "order": section.order,
                "accent_color": None,
                "origin": "card_sections",
            }
            for section in sorted(card_sections, key=lambda item: item.order)
            if section.content
        ]

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
                }
            )
    return sections
