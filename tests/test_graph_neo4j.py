"""Neo4j persistence: engagement isolation, load-back, purge. Skips if Neo4j is down."""
from __future__ import annotations

import types

import pytest

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.storage.graph import Neo4jGraph, TeeGraph, open_neo4j

URI, USER, PW = "bolt://localhost:7687", "neo4j", "weftpassword"


def _g(eng):
    return Neo4jGraph(URI, USER, PW, eng)


def _e(val, conf, src="m", etype=EntityType.EMAIL):
    return Entity.make(etype, val, source_module=src, confidence=conf, seed_id="s")


@pytest.fixture
def neo():
    g = _g("conn-check")
    try:
        g._connect().verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable")
    for e in ("WEFT-T1", "WEFT-T2"):
        _g(e).purge_engagement(e)
    yield
    for e in ("WEFT-T1", "WEFT-T2"):
        _g(e).purge_engagement(e)


# --- no-Neo4j tests (always run) ---

def test_tee_forwards_to_all():
    a, b = InMemoryGraph(), InMemoryGraph()
    tee = TeeGraph(a, b)
    e1, e2 = _e("x@y.com", 0.9), _e("z@y.com", 0.8)
    tee.upsert_entity(e1); tee.upsert_entity(e2); tee.link(e1, e2, via="m", confidence=0.8)
    assert e1.key() in a.nodes and e1.key() in b.nodes
    assert len(a.edges) == 1 and len(b.edges) == 1


def test_open_neo4j_none_when_unreachable():
    s = types.SimpleNamespace(neo4j_uri="bolt://127.0.0.1:9", neo4j_user="x", neo4j_password="y")
    assert open_neo4j(s, "ENG") is None


# --- Neo4j-backed tests ---

def test_engagement_isolation(neo):
    _g("WEFT-T1").upsert_entity(_e("shared@x.com", 0.9))
    _g("WEFT-T2").upsert_entity(_e("shared@x.com", 0.4))
    g1 = _g("WEFT-T1").load()
    g2 = _g("WEFT-T2").load()
    assert "email:shared@x.com" in g1.nodes
    assert "email:shared@x.com" in g2.nodes
    assert g1.nodes["email:shared@x.com"].confidence == 0.9   # each engagement its own node
    assert g2.nodes["email:shared@x.com"].confidence == 0.4


def test_link_persisted_and_loaded(neo):
    g = _g("WEFT-T1")
    a, b = _e("a@x.com", 0.9), _e("b@x.com", 0.8)
    g.upsert_entity(a); g.upsert_entity(b); g.link(a, b, via="gravatar", confidence=0.8)
    loaded = _g("WEFT-T1").load()
    assert loaded.neighbours("email:a@x.com") == ["email:b@x.com"]


def test_purge_clears_one_engagement_only(neo):
    _g("WEFT-T1").upsert_entity(_e("keep-not@x.com", 0.9))
    _g("WEFT-T2").upsert_entity(_e("survivor@x.com", 0.9))
    _g("WEFT-T1").purge_engagement("WEFT-T1")
    assert _g("WEFT-T1").load().nodes == {}
    assert "email:survivor@x.com" in _g("WEFT-T2").load().nodes
