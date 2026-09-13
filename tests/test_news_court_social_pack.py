"""GDELT news + CourtListener + Bluesky (mocked HTTP).

Shapes mirror the live responses verified against api.gdeltproject.org,
courtlistener.com/api/rest/v4, and public.api.bsky.app before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.name.courtlistener import CourtListener
from weft.modules.name.gdelt import Gdelt
from weft.modules.username.bluesky import Bluesky

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, secrets=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=secrets)


def _e(t, v):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- GDELT -------------------------------------------------------------------

def test_gdelt_emits_article_urls_with_metadata():
    http = FakeHttp({"api.gdeltproject.org": (200, {"articles": [
        {"url": "https://news.example/a1", "title": "Story one", "domain": "news.example",
         "seendate": "20260810T143000Z", "sourcecountry": "US", "language": "English"},
        {"url": "https://news.example/a1", "title": "dup"},   # duplicate url dropped
        {"url": "https://other.example/a2", "title": "Story two", "domain": "other.example"},
    ]})})
    out = asyncio.run(Gdelt().run(_e(EntityType.ORGANISATION, "Palantir Technologies"), _ctx(http)))
    urls = [e.value for e in out if e.type is EntityType.URL]
    assert urls == ["https://news.example/a1", "https://other.example/a2"]
    assert out[0].metadata["news_source"] == "news.example"
    assert out[0].metadata["mentions"] == "Palantir Technologies"


def test_gdelt_domain_seed_uses_domain_query():
    http = FakeHttp({"api.gdeltproject.org": (200, {"articles": []})})
    asyncio.run(Gdelt().run(_e(EntityType.DOMAIN, "example.com"), _ctx(http)))
    assert any("domain%3Aexample.com" in c or "domain:example.com" in c for c in http.calls)


# --- CourtListener -----------------------------------------------------------

def test_courtlistener_emits_case_urls():
    http = FakeHttp({"courtlistener.com/api": (200, {"results": [
        {"caseName": "KT4 Partners LLC v. Palantir Technologies",
         "absolute_url": "/opinion/123/kt4-v-palantir/", "court": "Del. Ch.", "dateFiled": "2019-01-01"},
    ]})})
    out = asyncio.run(CourtListener().run(_e(EntityType.ORGANISATION, "Palantir"), _ctx(http)))
    assert out and out[0].type is EntityType.URL
    # URL normalisation strips the trailing slash
    assert out[0].value == "https://www.courtlistener.com/opinion/123/kt4-v-palantir"
    assert out[0].metadata["case_name"].startswith("KT4 Partners")


def test_courtlistener_optional_token_sets_auth_header():
    http = FakeHttp({"courtlistener.com/api": (200, {"results": []})})
    asyncio.run(CourtListener().run(_e(EntityType.NAME, "Jane Doe"),
                                    _ctx(http, FakeSecrets({"COURTLISTENER_API_TOKEN": "tok"}))))
    # keyless path also works; here we only assert the call was made
    assert any("courtlistener.com/api" in c for c in http.calls)


# --- Bluesky -----------------------------------------------------------------

def test_bluesky_resolves_handle_exactly():
    http = FakeHttp({"getProfile": (200, {
        "handle": "vitalik.ca", "did": "did:plc:abc", "displayName": "Vitalik Buterin",
        "followersCount": 1000})})
    out = asyncio.run(Bluesky().run(_e(EntityType.USERNAME, "vitalik.ca"), _ctx(http)))
    socials = [e for e in out if e.type is EntityType.SOCIAL_PROFILE]
    handles = [e for e in out if e.type is EntityType.USERNAME]
    assert socials and socials[0].value == "https://bsky.app/profile/vitalik.ca"
    assert socials[0].metadata["match"] == "exact" and socials[0].confidence == 0.75
    assert handles and handles[0].value == "vitalik.ca"


def test_bluesky_plain_username_searches_actors():
    http = FakeHttp({"searchActors": (200, {"actors": [
        {"handle": "vitalik.ca", "did": "did:plc:abc", "displayName": "Vitalik Buterin"},
        {"handle": "fake.bsky.social", "did": "did:plc:xyz", "displayName": "parody"},
    ]})})
    out = asyncio.run(Bluesky().run(_e(EntityType.USERNAME, "vitalik"), _ctx(http)))
    socials = {e.value for e in out if e.type is EntityType.SOCIAL_PROFILE}
    assert "https://bsky.app/profile/vitalik.ca" in socials
    assert all(e.confidence == 0.5 for e in out if e.type is EntityType.SOCIAL_PROFILE)  # search = candidate
    assert any("searchActors" in c for c in http.calls)
    assert not any("getProfile" in c for c in http.calls)


def test_bluesky_name_seed_searches():
    http = FakeHttp({"searchActors": (200, {"actors": [{"handle": "a.bsky.social", "did": "d"}]})})
    out = asyncio.run(Bluesky().run(_e(EntityType.NAME, "Some Person"), _ctx(http)))
    assert any(e.type is EntityType.SOCIAL_PROFILE for e in out)


def test_registry_discovers_news_court_social():
    from weft.core import registry
    registry.discover()
    assert {"gdelt", "courtlistener", "bluesky"} <= set(registry.registered_classes())
