"""Deterministic correlation engine: each rule + provenance/confidence."""
from __future__ import annotations

from weft.core.correlation import CorrelationEngine, Finding
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph


def _e(etype, val, conf=0.9, src="m"):
    return Entity.make(etype, val, source_module=src, confidence=conf, seed_id="s")


def _rules(findings):
    return {f.rule for f in findings}


def test_multi_platform_presence():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://twitter.com/rob"))
    g.upsert_entity(_e(EntityType.URL, "https://github.com/rob"))
    f = [x for x in CorrelationEngine().run(g) if x.rule == "multi_platform_presence"]
    assert f and "2 platforms" in f[0].title


def test_corroborated_name_with_provenance():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.NAME, "Robert Huzo", src="companies_house"))
    g.upsert_entity(_e(EntityType.NAME, "Robert Huzo", src="github_user"))   # merges -> 2 sources
    f = [x for x in CorrelationEngine().run(g) if x.rule == "corroborated_name"][0]
    assert "companies_house" in f.sources and "github_user" in f.sources   # provenance
    assert f.confidence > 0.6


def test_person_organisation_link():
    g = InMemoryGraph()
    p = _e(EntityType.PERSON, "Robert Huzo"); o = _e(EntityType.ORGANISATION, "HuzoSec Ltd")
    g.upsert_entity(p); g.upsert_entity(o); g.link(p, o, via="companies_house", confidence=0.8)
    f = [x for x in CorrelationEngine().run(g) if x.rule == "person_organisation_link"]
    assert f and "HuzoSec Ltd" in f[0].detail


def test_email_to_accounts():
    g = InMemoryGraph()
    em = _e(EntityType.EMAIL, "rob@x.com")
    a1 = _e(EntityType.SOCIAL_PROFILE, "https://twitter.com/rob")
    a2 = _e(EntityType.USERNAME, "rob")
    for x in (em, a1, a2):
        g.upsert_entity(x)
    g.link(em, a1, via="gravatar", confidence=0.7); g.link(em, a2, via="gravatar", confidence=0.7)
    assert "email_to_accounts" in _rules(CorrelationEngine().run(g))


def test_geo_cluster():
    g = InMemoryGraph()
    for ip in ("1.1.1.1", "1.0.0.1"):
        g.upsert_entity(Entity(type=EntityType.IP, value=ip, source_module="ip_geolocation",
                               confidence=0.7, seed_id="s", metadata={"country": "Australia"}))
    f = [x for x in CorrelationEngine().run(g) if x.rule == "geo_cluster"]
    assert f and "Australia" in f[0].title


def test_hub_node():
    g = InMemoryGraph()
    hub = _e(EntityType.DOMAIN, "hub.com"); g.upsert_entity(hub)
    for i in range(4):
        c = _e(EntityType.IP, f"9.9.9.{i}"); g.upsert_entity(c); g.link(hub, c, via="dns", confidence=0.9)
    assert "hub_node" in _rules(CorrelationEngine().run(g))


def test_multi_source_anchor():
    g = InMemoryGraph()
    for src in ("crtsh", "certspotter", "wayback"):
        g.upsert_entity(_e(EntityType.DOMAIN, "api.x.com", src=src))   # 3 sources merged
    f = [x for x in CorrelationEngine().run(g) if x.rule == "multi_source_anchor"][0]
    assert len(f.sources) >= 3 and f.confidence >= 0.7


def test_engine_sorts_by_confidence_and_empty_graph():
    assert CorrelationEngine().run(InMemoryGraph()) == []
    g = InMemoryGraph()
    for src in ("a", "b", "c"):
        g.upsert_entity(_e(EntityType.EMAIL, "x@y.com", src=src))
    fs = CorrelationEngine().run(g)
    assert fs == sorted(fs, key=lambda f: f.confidence, reverse=True)


def test_report_includes_correlations():
    from datetime import date
    from weft.compliance.engagement import ControllerRole, Engagement
    from weft.core.reasoner import NullReasoner
    from weft.reporting.build import build_report
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://twitter.com/rob"))
    g.upsert_entity(_e(EntityType.URL, "https://github.com/rob"))
    eng = Engagement(id="E1", client="Acme", scope_ref="S", lawful_basis="LI", authorised_targets=["x"],
                     start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), controller_role=ControllerRole.PROCESSOR)
    md = build_report(eng, g, reasoner=NullReasoner())
    assert "## Findings (correlations)" in md
    assert "platforms" in md
