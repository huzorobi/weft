"""Native username checker + name->candidate generation."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.core.username_gen import candidates_from_name
from weft.modules.username.username_check import UsernameCheck

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=True, depth=0, http=http)


def _e(etype, val):
    return Entity.make(etype, val, source_module="seed", confidence=1.0, seed_id="s")


# --- name -> candidates ---
def test_candidates_from_name():
    c = candidates_from_name("Robert Huzo")
    assert "roberthuzo" in c
    assert "robert.huzo" in c
    assert "rhuzo" in c
    assert candidates_from_name("madonna") == ["madonna"]
    assert candidates_from_name("") == []


def test_candidates_capped():
    assert len(candidates_from_name("Robert James Huzo", cap=4)) == 4


# --- direct username check ---
def test_direct_username_hit_and_miss():
    http = FakeHttp({
        "github.com": (200, "profile ok"),
        "reddit.com": (200, "Sorry, nobody on Reddit goes by that name"),  # m_string -> miss
    })
    out = asyncio.run(UsernameCheck().run(_e(EntityType.USERNAME, "torvalds"), _ctx(http)))
    vals = {e.value for e in out}
    assert any("github.com/torvalds" in v for v in vals)      # hit
    assert not any("reddit.com" in v for v in vals)           # m_string -> miss
    assert all(e.type is EntityType.SOCIAL_PROFILE for e in out)
    assert all(not e.metadata.get("candidate") for e in out)  # direct, not candidate


def test_name_derived_candidates_are_low_conf_flagged():
    http = FakeHttp({"github.com": (200, "ok")})   # every candidate "hits" github in the mock
    out = asyncio.run(UsernameCheck().run(_e(EntityType.NAME, "Robert Huzo"), _ctx(http)))
    profiles = [e for e in out if e.type is EntityType.SOCIAL_PROFILE]
    usernames = [e for e in out if e.type is EntityType.USERNAME]
    assert profiles and all(p.metadata.get("candidate") and p.metadata.get("derived_from_name") == "Robert Huzo"
                            for p in profiles)
    assert usernames and all(u.metadata.get("candidate") for u in usernames)
    assert profiles[0].confidence < 0.6   # lower than a direct hit


def test_health_needs_http():
    from weft.core.module import RunContext as RC
    h = asyncio.run(UsernameCheck().health(RC(engagement_id="e", operator="o", allow_tos_risk=False, depth=0)))
    assert not h.ok


def test_registry_discovers_username_check():
    from weft.core import registry
    registry.discover()
    assert "username_check" in registry.registered_classes()
