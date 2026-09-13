"""GLEIF (company) + Wikidata (structured identity) — mocked HTTP."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.name.gleif import Gleif
from weft.modules.name.wikidata import Wikidata

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _name(v="Acme Ltd"):
    return Entity.make(EntityType.NAME, v, source_module="seed", confidence=1.0, seed_id="s")


def test_gleif_parses_org_and_address():
    http = FakeHttp({"gleif.org": (200, {"data": [
        {"attributes": {"lei": "LEI123", "entity": {
            "legalName": {"name": "Acme Ltd"},
            "legalAddress": {"addressLines": ["1 High St"], "city": "London", "country": "GB"}}}},
    ]})})
    out = asyncio.run(Gleif().run(_name(), _ctx(http)))
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    addrs = [e for e in out if e.type is EntityType.ADDRESS]
    assert orgs and orgs[0].value == "Acme Ltd" and orgs[0].metadata["lei"] == "LEI123"
    assert addrs and "London" in addrs[0].value


def test_wikidata_search_and_claims():
    http = FakeHttp({
        "wbsearchentities": (200, {"search": [
            {"id": "Q34253", "label": "Linus Torvalds", "description": "software engineer",
             "concepturi": "http://www.wikidata.org/entity/Q34253"}]}),
        "wbgetentities": (200, {"entities": {"Q34253": {"claims": {
            "P856": [{"mainsnak": {"datavalue": {"value": "https://torvalds.example"}}}],
            "P2037": [{"mainsnak": {"datavalue": {"value": "torvalds"}}}],
        }}}}),
    })
    out = asyncio.run(Wikidata().run(_name("Linus Torvalds"), _ctx(http)))
    persons = [e for e in out if e.type is EntityType.PERSON]
    urls = {e.value for e in out if e.type is EntityType.URL}
    socials = {e.value for e in out if e.type is EntityType.SOCIAL_PROFILE}
    assert persons and persons[0].value == "Linus Torvalds"
    assert "https://torvalds.example" in urls
    assert "https://github.com/torvalds" in socials


def test_wikidata_no_match_returns_empty():
    out = asyncio.run(Wikidata().run(_name("zzz"), _ctx(FakeHttp({"wbsearchentities": (200, {"search": []})}))))
    assert out == []


def test_registry_discovers_identity_sources():
    from weft.core import registry
    registry.discover()
    assert {"gleif", "wikidata"} <= set(registry.registered_classes())
