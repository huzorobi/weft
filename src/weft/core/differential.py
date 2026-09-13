"""Differential runs — what changed since the last run.

Weft persists a graph per engagement, so re-running a seed turns Weft into a monitoring tool:
this compares a previous run's snapshot against the current graph and reports what is new, what
disappeared, and which entities gained confidence. Snapshots are plain JSON, so a run can save
one and the next run diff against it. Pure and deterministic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import Edge, InMemoryGraph


@dataclass
class GraphDiff:
    added: list[Entity] = field(default_factory=list)          # entities new this run
    removed_keys: list[str] = field(default_factory=list)      # entity keys gone this run
    confidence_up: list[tuple[str, float, float]] = field(default_factory=list)  # (key, old, new)
    added_edges: list[Edge] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed_keys or self.confidence_up or self.added_edges)


def snapshot_graph(graph: InMemoryGraph) -> dict:
    """Serialise a graph to a JSON-safe dict (nodes + edges)."""
    return {
        "nodes": [
            {"type": e.type.value, "value": e.value, "source_module": e.source_module,
             "confidence": e.confidence, "seed_id": e.seed_id, "metadata": e.metadata, "label": e.label}
            for e in graph.nodes.values()
        ],
        "edges": [{"src": ed.src_key, "dst": ed.dst_key, "via": ed.via, "confidence": ed.confidence}
                  for ed in graph.edges],
    }


def graph_from_snapshot(snap: dict) -> InMemoryGraph:
    g = InMemoryGraph()
    for n in snap.get("nodes", []):
        g.nodes[f"{n['type']}:{n['value'].lower().strip()}"] = Entity(
            type=EntityType(n["type"]), value=n["value"], source_module=n["source_module"],
            confidence=n["confidence"], seed_id=n["seed_id"],
            metadata=n.get("metadata") or {}, label=n.get("label"))
    for ed in snap.get("edges", []):
        g.edges.append(Edge(ed["src"], ed["dst"], ed["via"], ed["confidence"]))
    return g


def save_snapshot(graph: InMemoryGraph, path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot_graph(graph), fh)
    return path


def load_snapshot(path: str) -> InMemoryGraph:
    with open(path, encoding="utf-8") as fh:
        return graph_from_snapshot(json.load(fh))


def diff_graphs(previous: InMemoryGraph, current: InMemoryGraph, *, conf_delta: float = 0.05) -> GraphDiff:
    """Compare a previous graph against the current one."""
    diff = GraphDiff()
    prev_nodes, cur_nodes = previous.nodes, current.nodes
    for key, e in cur_nodes.items():
        if key not in prev_nodes:
            diff.added.append(e)
        elif e.confidence - prev_nodes[key].confidence >= conf_delta:
            diff.confidence_up.append((key, prev_nodes[key].confidence, e.confidence))
    diff.removed_keys = [k for k in prev_nodes if k not in cur_nodes]
    prev_edges = {(ed.src_key, ed.dst_key, ed.via) for ed in previous.edges}
    diff.added_edges = [ed for ed in current.edges if (ed.src_key, ed.dst_key, ed.via) not in prev_edges]
    return diff


def render_diff(diff: GraphDiff) -> list[str]:
    """Render the diff as Markdown lines for the report (empty if nothing changed)."""
    if not diff.changed:
        return ["_No changes since the last run._"]
    out: list[str] = []
    if diff.added:
        out.append(f"- **{len(diff.added)} new** entities since last run: "
                   + ", ".join(f"`{e.value}` ({e.type.value})" for e in diff.added[:12])
                   + (" …" if len(diff.added) > 12 else ""))
    if diff.removed_keys:
        out.append(f"- **{len(diff.removed_keys)} gone** (not re-observed): "
                   + ", ".join(f"`{k}`" for k in diff.removed_keys[:12])
                   + (" …" if len(diff.removed_keys) > 12 else ""))
    for key, old, new in diff.confidence_up[:10]:
        out.append(f"- **Confidence up**: `{key}` {old:.2f} → {new:.2f}")
    if diff.added_edges:
        out.append(f"- **{len(diff.added_edges)} new** relationship(s).")
    return out
