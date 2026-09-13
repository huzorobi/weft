"""The entity graph store (Neo4j).

Entities are nodes; links are ``(:Entity)-[:LINKS_TO {via, confidence}]->(:Entity)``
relationships. The store is written to as the orchestrator discovers entities.

The driver connects lazily, so importing this module (and constructing the store)
never requires a live database — the connection opens on first use. This keeps the
package importable for unit tests that do not exercise the graph.

Used from Phase 1 onward.
"""
from __future__ import annotations

from weft.core.entity import Entity


class Neo4jGraph:
    def __init__(self, uri: str, user: str, password: str):
        self._uri = uri
        self._auth = (user, password)
        self._driver = None

    def _connect(self):
        if self._driver is None:
            from neo4j import GraphDatabase  # imported lazily so tests need no driver

            self._driver = GraphDatabase.driver(self._uri, auth=self._auth)
        return self._driver

    def upsert_entity(self, entity: Entity) -> None:
        driver = self._connect()
        with driver.session() as s:
            s.run(
                """
                MERGE (e:Entity {key: $key})
                SET e.type = $type, e.value = $value, e.label = $label,
                    e.confidence = CASE WHEN e.confidence IS NULL OR $confidence > e.confidence
                                        THEN $confidence ELSE e.confidence END,
                    e.sources = CASE WHEN $source IN coalesce(e.sources, [])
                                     THEN e.sources ELSE coalesce(e.sources, []) + $source END
                """,
                key=entity.key(), type=entity.type.value, value=entity.value,
                label=entity.label, confidence=entity.confidence,
                source=entity.source_module,
            )

    def link(self, src: Entity, dst: Entity, *, via: str, confidence: float) -> None:
        driver = self._connect()
        with driver.session() as s:
            s.run(
                """
                MATCH (a:Entity {key: $a}), (b:Entity {key: $b})
                MERGE (a)-[r:LINKS_TO {via: $via}]->(b)
                SET r.confidence = $confidence
                """,
                a=src.key(), b=dst.key(), via=via, confidence=confidence,
            )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
