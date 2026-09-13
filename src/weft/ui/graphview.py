"""Turn a graph into a renderable payload, and render it with pyvis.

``build_vis_payload`` is pure and testable: it converts an :class:`InMemoryGraph`
into vis.js-style node and edge dicts, applies the confidence filter (dropping
low-confidence nodes and any edge that loses an endpoint), and colours nodes by
entity type. ``render_html`` wraps pyvis and is imported lazily so the payload logic
can be tested without the rendering dependency.
"""
from __future__ import annotations

from weft.core.entity import EntityType
from weft.core.graphstore import InMemoryGraph

# One colour per entity type. Kept distinct and readable on a light canvas.
TYPE_COLOURS: dict[str, str] = {
    EntityType.PHONE.value: "#2563eb",
    EntityType.EMAIL.value: "#dc2626",
    EntityType.USERNAME.value: "#7c3aed",
    EntityType.NAME.value: "#0891b2",
    EntityType.PERSON.value: "#0e7490",
    EntityType.DOMAIN.value: "#059669",
    EntityType.ORGANISATION.value: "#d97706",
    EntityType.ADDRESS.value: "#b45309",
    EntityType.URL.value: "#65a30d",
    EntityType.SOCIAL_PROFILE.value: "#db2777",
    EntityType.IP.value: "#475569",
    EntityType.IMAGE.value: "#9333ea",
    EntityType.ARCHIVE_SNAPSHOT.value: "#78716c",
    EntityType.BREACH.value: "#991b1b",
}
DEFAULT_COLOUR = "#94a3b8"


def colour_for(entity_type: EntityType) -> str:
    return TYPE_COLOURS.get(entity_type.value, DEFAULT_COLOUR)


def _tooltip(entity) -> str:
    lines = [f"{entity.type.value}: {entity.value}", f"confidence: {entity.confidence:.2f}"]
    sources = entity.metadata.get("sources")
    if sources:
        lines.append("sources: " + ", ".join(sources))
    for k, v in entity.metadata.items():
        if k == "sources":
            continue
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def build_vis_payload(graph: InMemoryGraph, *, min_confidence: float = 0.0) -> dict:
    nodes = []
    kept: set[str] = set()
    for key, entity in graph.nodes.items():
        if entity.confidence < min_confidence:
            continue
        kept.add(key)
        nodes.append({
            "id": key,
            "label": (entity.label or entity.value)[:40],
            "group": entity.type.value,
            "color": colour_for(entity.type),
            "title": _tooltip(entity),
            "value": round(entity.confidence, 3),
        })
    edges = [
        {"from": e.src_key, "to": e.dst_key, "label": e.via, "confidence": round(e.confidence, 3)}
        for e in graph.edges
        if e.src_key in kept and e.dst_key in kept
    ]
    return {"nodes": nodes, "edges": edges}


def render_html(payload: dict, *, height: str = "600px") -> str:
    """Render the payload to standalone HTML via pyvis."""
    from pyvis.network import Network

    net = Network(height=height, width="100%", bgcolor="#ffffff", font_color="#111827", directed=True)
    net.barnes_hut(gravity=-8000, spring_length=120)
    for node in payload["nodes"]:
        net.add_node(node["id"], label=node["label"], color=node["color"],
                     title=node["title"], value=node["value"], group=node["group"])
    for edge in payload["edges"]:
        net.add_edge(edge["from"], edge["to"], label=edge["label"], title=f"confidence {edge['confidence']}")
    return net.generate_html(notebook=False)
