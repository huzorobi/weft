"""subdomain.center + Crossref + Apple iTunes (mocked HTTP).

Shapes mirror the live responses verified against api.subdomain.center, api.crossref.org, and
itunes.apple.com before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.subdomain_center import SubdomainCenter
from weft.modules.name.apple_itunes import AppleItunes
from weft.modules.name.crossref import Crossref

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _e(t, v):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- subdomain.center --------------------------------------------------------

def test_subdomain_center_emits_subdomains():
    http = FakeHttp({"api.subdomain.center": (200, ["a.github.com", "b.github.com", "github.com", "a.github.com"])})
    out = asyncio.run(SubdomainCenter().run(_e(EntityType.DOMAIN, "github.com"), _ctx(http)))
    subs = {e.value for e in out if e.type is EntityType.DOMAIN}
    assert subs == {"a.github.com", "b.github.com"}   # parent + duplicate dropped


def test_subdomain_center_non_list_returns_empty():
    assert asyncio.run(SubdomainCenter().run(_e(EntityType.DOMAIN, "x.com"),
                                             _ctx(FakeHttp({"api.subdomain.center": (200, {"error": "x"})})))) == []


# --- Crossref ----------------------------------------------------------------

def test_crossref_emits_doi_urls_with_metadata():
    http = FakeHttp({"api.crossref.org": (200, {"message": {"items": [
        {"DOI": "10.1000/abc", "title": ["A Study"], "publisher": "ACM", "type": "journal-article",
         "published": {"date-parts": [[2021, 5]]}},
        {"DOI": "10.1000/abc", "title": ["dup"]},   # duplicate DOI dropped
    ]}})})
    out = asyncio.run(Crossref().run(_e(EntityType.ORGANISATION, "Palantir"), _ctx(http)))
    assert len(out) == 1 and out[0].value == "https://doi.org/10.1000/abc"
    assert out[0].metadata["title"] == "A Study"
    assert out[0].metadata["year"] == 2021


def test_crossref_no_items_returns_empty():
    assert asyncio.run(Crossref().run(_e(EntityType.NAME, "Nobody"),
                                      _ctx(FakeHttp({"api.crossref.org": (200, {"message": {"items": []}})})))) == []


# --- Apple iTunes ------------------------------------------------------------

def test_itunes_keeps_relevant_apps_and_seller():
    http = FakeHttp({"itunes.apple.com/search": (200, {"results": [
        {"trackName": "Telegram Messenger", "sellerName": "Telegram FZ-LLC", "artistName": "Telegram FZ-LLC",
         "bundleId": "ph.telegra.Telegraph", "trackViewUrl": "https://apps.apple.com/app/id1"},
        {"trackName": "Instagram", "sellerName": "Instagram, Inc.", "artistName": "Instagram, Inc.",
         "bundleId": "com.burbn.instagram", "trackViewUrl": "https://apps.apple.com/app/id2"},  # irrelevant
    ]})})
    out = asyncio.run(AppleItunes().run(_e(EntityType.ORGANISATION, "Telegram"), _ctx(http)))
    urls = {e.value for e in out if e.type is EntityType.URL}
    orgs = {e.value for e in out if e.type is EntityType.ORGANISATION}
    assert urls == {"https://apps.apple.com/app/id1"}       # Instagram filtered out
    assert "Telegram FZ-LLC" in orgs
    assert not any("Instagram" in o for o in orgs)


def test_itunes_no_results_returns_empty():
    assert asyncio.run(AppleItunes().run(_e(EntityType.ORGANISATION, "Zzz"),
                                         _ctx(FakeHttp({"itunes.apple.com/search": (200, {"results": []})})))) == []


def test_registry_discovers_surface_footprint_pack():
    from weft.core import registry
    registry.discover()
    assert {"subdomain_center", "crossref", "apple_itunes"} <= set(registry.registered_classes())
