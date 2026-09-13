"""The entity graph store (Neo4j), plus a tee and an in-memory fallback selector.

Entities are nodes; links are ``(:Entity)-[:LINKS_TO {via, confidence}]->(:Entity)``.
Nodes are **scoped to an engagement** — keyed by ``(engagement, key)`` — so two
engagements never share a node, which keeps one client's data out of another's
(the same isolation the compliance model requires). ``load`` reads an engagement's
graph back for reporting; ``purge_engagement`` deletes it.

The driver connects lazily, so importing this module never needs a live database.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import GraphStore, InMemoryGraph


class Neo4jGraph:
    """Engagement-scoped Neo4j graph store."""

    def __init__(self, uri: str, user: str, password: str, engagement_id: str):
        self._uri = uri
        self._auth = (user, password)
        self._engagement = engagement_id
        self._driver = None

    def _connect(self):
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self._uri, auth=self._auth)
        return self._driver

    def upsert_entity(self, entity: Entity) -> None:
        with self._connect().session() as s:
            s.run(
                """
                MERGE (e:Entity {engagement: $eng, key: $key})
                SET e.type = $type, e.value = $value, e.label = $label,
                    e.confidence = CASE WHEN e.confidence IS NULL OR $confidence > e.confidence
                                        THEN $confidence ELSE e.confidence END,
                    e.sources = CASE WHEN $source IN coalesce(e.sources, [])
                                     THEN e.sources ELSE coalesce(e.sources, []) + $source END
                """,
                eng=self._engagement, key=entity.key(), type=entity.type.value, value=entity.value,
                label=entity.label, confidence=entity.confidence, source=entity.source_module,
            )

    def link(self, src: Entity, dst: Entity, *, via: str, confidence: float) -> None:
        with self._connect().session() as s:
            s.run(
                """
                MATCH (a:Entity {engagement: $eng, key: $a}), (b:Entity {engagement: $eng, key: $b})
                MERGE (a)-[r:LINKS_TO {via: $via}]->(b)
                SET r.confidence = $confidence
                """,
                eng=self._engagement, a=src.key(), b=dst.key(), via=via, confidence=confidence,
            )

    def load(self) -> InMemoryGraph:
        """Read this engagement's persisted graph back into an in-memory graph."""
        g = InMemoryGraph()
        with self._connect().session() as s:
            for rec in s.run("MATCH (e:Entity {engagement: $eng}) RETURN e", eng=self._engagement):
                n = rec["e"]
                try:
                    etype = EntityType(n["type"])
                except Exception:
                    continue
                g.upsert_entity(Entity(
                    type=etype, value=n["value"], source_module=(n.get("sources") or ["neo4j"])[0],
                    confidence=n.get("confidence", 0.5), seed_id="", label=n.get("label"),
                    metadata={"sources": list(n.get("sources") or [])},
                ))
            for rec in s.run(
                "MATCH (a:Entity {engagement: $eng})-[r:LINKS_TO]->(b:Entity {engagement: $eng}) "
                "RETURN a.key AS a, b.key AS b, r.via AS via, r.confidence AS c", eng=self._engagement):
                from weft.core.graphstore import Edge
                g.edges.append(Edge(rec["a"], rec["b"], rec["via"], rec["c"] or 0.0))
        return g

    def purge_engagement(self, engagement_id: str) -> None:
        with self._connect().session() as s:
            s.run("MATCH (e:Entity {engagement: $eng}) DETACH DELETE e", eng=engagement_id)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


class TeeGraph:
    """Forwards writes to several stores — persist to Neo4j while rendering from memory."""

    def __init__(self, *stores: GraphStore):
        self._stores = [s for s in stores if s is not None]

    def upsert_entity(self, entity: Entity) -> None:
        for s in self._stores:
            s.upsert_entity(entity)

    def link(self, src: Entity, dst: Entity, *, via: str, confidence: float) -> None:
        for s in self._stores:
            s.link(src, dst, via=via, confidence=confidence)


def open_neo4j(settings, engagement_id: str) -> Neo4jGraph | None:
    """Return a connected Neo4jGraph for the engagement, or None if Neo4j is unreachable."""
    try:
        g = Neo4jGraph(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, engagement_id)
        g._connect().verify_connectivity()
        return g
    except Exception:
        return None
