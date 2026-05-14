from __future__ import annotations

from pathlib import Path

from brain_ds.ontology import Graph

from .theme import BACKGROUND_COLOR, color_for_type, vis_options_json


def _load_network_class():
    try:
        from pyvis.network import Network
    except ImportError:
        return None
    return Network


def build_network(graph: Graph | dict, network_cls) -> object:
    if isinstance(graph, dict):
        graph = Graph.from_v1(graph)
    net = network_cls(
        height="85vh",
        width="100%",
        directed=True,
        notebook=False,
        bgcolor=BACKGROUND_COLOR,
        font_color="#e2e8f0",
    )
    net.set_options(vis_options_json())

    for node in graph.nodes:
        if not node.id:
            continue
        color = color_for_type(node.type.value)
        net.add_node(
            n_id=node.id,
            label=node.label or node.id,
            title=_node_title(
                details=node.details or {},
                card_sections=[
                    {
                        "title": section.title,
                        "content": section.content,
                        "order": section.order,
                    }
                    for section in (node.card_sections or [])
                ],
            ),
            color=color,
            group=node.type.value,
        )

    for edge in graph.edges:
        if not edge.source or not edge.target:
            continue
        reasons = "; ".join(edge.reasons or [])
        edge_title = edge.label.value
        if reasons:
            edge_title = f"{edge_title} — {reasons}"
        width = 1.0 + ((edge.weight or 0.0) * 4.0)
        net.add_edge(
            edge.source,
            edge.target,
            title=edge_title,
            label=edge.label.value,
            width=width,
        )

    return net


def render_simple_html(
    graph: Graph,
    *,
    output_path: Path,
    open_browser: bool = False,
    network_cls: type | None = None,
) -> Path:
    cls = network_cls or _load_network_class()
    if cls is None:
        raise RuntimeError("pyvis missing")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    net = build_network(graph, cls)
    net.write_html(str(output_path), notebook=False, open_browser=False)

    if open_browser:
        try:
            import webbrowser

            opened = webbrowser.open(output_path.as_uri())
            if not opened:
                print(f"HTML viewer generated: {output_path}")
        except Exception:
            print(f"HTML viewer generated: {output_path}")

    return output_path


def _node_title(details: dict | None = None, *, card_sections: list[dict] | None = None) -> str:
    details = details or {}
    if card_sections:
        parts = [
            f"<b>{section.get('title', '')}</b>: {section.get('content', '')}"
            for section in sorted(card_sections, key=lambda item: item.get("order", 0))
        ]
        return "<br>".join(parts)
    return (
        f"<b>What</b>: {details.get('what', '')}<br>"
        f"<b>Why</b>: {details.get('why', '')}<br>"
        f"<b>Where</b>: {details.get('where', '')}<br>"
        f"<b>Learned</b>: {details.get('learned', '')}"
    )
