#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

from brain_ds.ontology import EntityType, TYPE_COLORS


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "org"


def node_title(details: dict) -> str:
    what = details.get("what", "")
    why = details.get("why", "")
    where = details.get("where", "")
    learned = details.get("learned", "")
    return (
        f"<b>What</b>: {what}<br>"
        f"<b>Why</b>: {why}<br>"
        f"<b>Where</b>: {where}<br>"
        f"<b>Learned</b>: {learned}"
    )


def _load_network_class():
    try:
        from pyvis.network import Network
    except ImportError:
        return None
    return Network


def build_network(graph: dict, network_cls) -> object:
    net = network_cls(height="800px", width="100%", directed=True, notebook=False)
    net.set_options(
        """
        {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "hubsize",
              "nodeSpacing": 190,
              "treeSpacing": 260
            }
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true,
            "tooltipDelay": 120
          },
          "physics": {
            "enabled": false
          },
          "edges": {
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.7 } },
            "smooth": { "enabled": true, "type": "cubicBezier" },
            "font": { "size": 11, "align": "middle" }
          },
          "nodes": {
            "shape": "dot",
            "size": 16,
            "font": { "size": 13 }
          }
        }
        """
    )

    for node in graph.get("nodes", []):
        node_id = node.get("id")
        if not node_id:
            continue
        node_type = node.get("type", "Unknown")
        resolved_type = EntityType.from_string(node_type)
        details = node.get("details") or {}
        color = TYPE_COLORS.get(resolved_type.value, EntityType.UNKNOWN.color)

        net.add_node(
            n_id=node_id,
            label=node.get("label", node_id),
            title=node_title(details),
            color=color,
            group=resolved_type.value,
        )

    for edge in graph.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        net.add_edge(source, target, title=edge.get("label", ""), label=edge.get("label", ""))

    return net


def derive_output_path(json_path: Path, graph: dict) -> Path:
    org = str(graph.get("org", "org"))
    return json_path.with_name(f"{slugify(org)}-graph.html")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_viewer.py <path-to-graph-json>", file=sys.stderr)
        return 2

    json_path = Path(sys.argv[1]).resolve()
    if not json_path.exists():
        print(f"JSON file not found: {json_path}", file=sys.stderr)
        return 2

    try:
        with json_path.open("r", encoding="utf-8") as f:
            graph = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 2

    network_cls = _load_network_class()
    if network_cls is None:
        print(
            "pyvis is not installed. Install it with: uv sync",
            file=sys.stderr,
        )
        return 1

    net = build_network(graph, network_cls)
    output_path = derive_output_path(json_path, graph)
    net.write_html(str(output_path), notebook=False, open_browser=False)

    print(f"HTML viewer generated: {output_path}")
    print(f"Graph JSON used: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
