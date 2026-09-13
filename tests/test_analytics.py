"""Graph analytics: betweenness (gatekeepers) + community detection."""
from __future__ import annotations

from weft.core.analytics import betweenness_centrality, communities, graph_analytics
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph


def _n(v):
    return Entity.make(EntityType.DOMAIN, v, source_module="m", confidence=0.9, seed_id="s")


def _path_graph(labels):
    g = InMemoryGraph()
    ents = [_n(x) for x in labels]
    for e in ents:
        g.upsert_entity(e)
    for a, b in zip(ents, ents[1:]):
        g.link(a, b, via="m", confidence=0.9)
    return g, ents


def test_betweenness_path_middle_is_highest():
    g, ents = _path_graph("abcde")   # a-b-c-d-e
    from weft.core.analytics import _adjacency
    cb = betweenness_centrality(_adjacency(g))
    keys = {e.value.split(".")[0] if "." in e.value else e.value: cb[e.key()] for e in ents}
    # c (middle) strictly highest; endpoints zero
    order = sorted(cb.items(), key=lambda kv: kv[1], reverse=True)
    top_key = order[0][0]
    assert top_key == ents[2].key()          # 'c' is the gatekeeper
    assert cb[ents[0].key()] == 0.0 and cb[ents[4].key()] == 0.0


def test_communities_two_components():
    g = InMemoryGraph()
    a, b, c, d = _n("a.com"), _n("b.com"), _n("c.com"), _n("d.com")
    for e in (a, b, c, d):
        g.upsert_entity(e)
    g.link(a, b, via="m", confidence=0.9)     # component 1: a-b
    g.link(c, d, via="m", confidence=0.9)     # component 2: c-d
    from weft.core.analytics import _adjacency
    comms = communities(_adjacency(g))
    assert len(comms) == 2
    assert all(len(x) == 2 for x in comms)


def test_graph_analytics_ranks_pivots():
    g, ents = _path_graph("abcde")
    a = graph_analytics(g)
    assert a.pivots and a.pivots[0][0] == ents[2].key()
    assert len(a.communities) == 1            # one connected component


def test_empty_graph():
    a = graph_analytics(InMemoryGraph())
    assert a.pivots == [] and a.communities == []


def test_report_includes_analytics():
    from datetime import date
    from weft.compliance.engagement import ControllerRole, Engagement
    from weft.core.reasoner import NullReasoner
    from weft.reporting.build import build_report
    g, _ = _path_graph("abcde")
    eng = Engagement(id="E", client="Acme", scope_ref="S", lawful_basis="LI", authorised_targets=["x"],
                     start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), controller_role=ControllerRole.PROCESSOR)
    md = build_report(eng, g, reasoner=NullReasoner())
    assert "## Graph analytics" in md
