"""The graph-store interface and an in-memory implementation.

The orchestrator writes to a :class:`GraphStore`. Production uses Neo4j
(:class:`weft.storage.graph.Neo4jGraph`); tests and inspection use
:class:`InMemoryGraph`, which merges duplicate nodes with the scoring rules and keeps
the edges so a run's graph shape can be asserted without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from weft.core.entity import Entity
from weft.core.scoring import merge


class GraphStore(Protocol):
    def upsert_entity(self, entity: Entity) -> None: ...
    def link(self, src: Entity, dst: Entity, *, via: str, confidence: float) -> None: ...


@dataclass(frozen=True)
class Edge:
    src_key: str
    dst_key: str
    via: str
    confidence: float


class InMemoryGraph:
    """A process-local graph. Nodes keyed by ``Entity.key()``, merged on collision."""

    def __init__(self) -> None:
        self.nodes: dict[str, Entity] = {}
        self.edges: list[Edge] = []

    def upsert_entity(self, entity: Entity) -> None:
        key = entity.key()
        if key in self.nodes:
            self.nodes[key] = merge(self.nodes[key], entity)
        else:
            md = dict(entity.metadata)
            md.setdefault("sources", [entity.source_module])
            self.nodes[key] = Entity(
                type=entity.type, value=entity.value, source_module=entity.source_module,
                confidence=entity.confidence, seed_id=entity.seed_id, metadata=md, label=entity.label,
            )

    def link(self, src: Entity, dst: Entity, *, via: str, confidence: float) -> None:
        self.edges.append(Edge(src.key(), dst.key(), via, confidence))

    # convenience for tests / UI
    def neighbours(self, key: str) -> list[str]:
        return [e.dst_key for e in self.edges if e.src_key == key]
