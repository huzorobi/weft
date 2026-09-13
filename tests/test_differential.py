"""Differential runs — snapshot round-trip + graph diff + render."""
from __future__ import annotations

from weft.core.differential import (
    diff_graphs,
    graph_from_snapshot,
    render_diff,
    snapshot_graph,
)
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph


def _e(t, v, conf=0.9, src="m", meta=None):
    return Entity.make(t, v, source_module=src, confidence=conf, seed_id="s", metadata=meta or {})


def test_snapshot_roundtrip_preserves_nodes_and_edges():
    g = InMemoryGraph()
    a = _e(EntityType.EMAIL, "rob@x.com"); b = _e(EntityType.DOMAIN, "x.com")
    g.upsert_entity(a); g.upsert_entity(b); g.link(a, b, via="whois", confidence=0.8)
    restored = graph_from_snapshot(snapshot_graph(g))
    assert set(restored.nodes) == set(g.nodes)
    assert len(restored.edges) == 1 and restored.edges[0].via == "whois"
    assert restored.nodes["email:rob@x.com"].confidence == 0.9


def test_diff_detects_added_removed_and_confidence():
    prev = InMemoryGraph()
    prev.upsert_entity(_e(EntityType.EMAIL, "rob@x.com", conf=0.5))
    prev.upsert_entity(_e(EntityType.DOMAIN, "old.com"))
    cur = InMemoryGraph()
    cur.upsert_entity(_e(EntityType.EMAIL, "rob@x.com", conf=0.9))   # confidence up
    cur.upsert_entity(_e(EntityType.USERNAME, "rob"))               # new
    # old.com removed
    diff = diff_graphs(prev, cur)
    assert {e.value for e in diff.added} == {"rob"}
    assert diff.removed_keys == ["domain:old.com"]
    assert diff.confidence_up and diff.confidence_up[0][1] == 0.5 and diff.confidence_up[0][2] == 0.9
    assert diff.changed


def test_diff_no_change():
    g = InMemoryGraph(); g.upsert_entity(_e(EntityType.EMAIL, "a@b.com"))
    g2 = InMemoryGraph(); g2.upsert_entity(_e(EntityType.EMAIL, "a@b.com"))
    diff = diff_graphs(g, g2)
    assert not diff.changed
    assert render_diff(diff) == ["_No changes since the last run._"]


def test_render_diff_lists_changes():
    prev = InMemoryGraph()
    cur = InMemoryGraph(); cur.upsert_entity(_e(EntityType.USERNAME, "newguy"))
    lines = render_diff(diff_graphs(prev, cur))
    assert any("1 new" in l and "newguy" in l for l in lines)
