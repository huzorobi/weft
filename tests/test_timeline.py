"""Timeline construction from graph temporal metadata."""
from __future__ import annotations

from datetime import date

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.reporting.timeline import build_timeline, _norm_date


def test_norm_date():
    assert _norm_date("20260807104456") == "2026-08-07"
    assert _norm_date("1995-08-14T04:00:00Z") == "1995-08-14"
    assert _norm_date("nonsense") is None


def test_build_timeline_sorted():
    g = InMemoryGraph()
    g.upsert_entity(Entity(type=EntityType.DOMAIN, value="example.com", source_module="rdap_whois",
                           confidence=0.9, seed_id="s",
                           metadata={"registration_events": {"registration": "1995-08-14T04:00:00Z",
                                                             "expiration": "2027-08-13T04:00:00Z"}}))
    g.upsert_entity(Entity(type=EntityType.URL, value="http://example.com/old", source_module="wayback",
                           confidence=0.8, seed_id="s", metadata={"first_snapshot": "20020120142510"}))
    tl = build_timeline(g)
    dates = [t.date for t in tl]
    assert dates == sorted(dates)
    assert "1995-08-14" in dates and "2002-01-20" in dates
    assert any("registration of example.com" in t.event for t in tl)


def test_report_includes_timeline():
    from weft.compliance.engagement import ControllerRole, Engagement
    from weft.core.reasoner import NullReasoner
    from weft.reporting.build import build_report
    g = InMemoryGraph()
    g.upsert_entity(Entity(type=EntityType.DOMAIN, value="x.com", source_module="rdap_whois", confidence=0.9,
                           seed_id="s", metadata={"registration_events": {"registration": "2001-01-01T00:00:00Z"}}))
    eng = Engagement(id="E", client="Acme", scope_ref="S", lawful_basis="LI", authorised_targets=["x.com"],
                     start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), controller_role=ControllerRole.PROCESSOR)
    md = build_report(eng, g, reasoner=NullReasoner())
    assert "## Timeline" in md and "2001-01-01" in md
