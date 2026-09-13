"""Phase 4 search/historical modules against mocked HTTP / sample output."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.wayback import Wayback
from weft.modules.phone.phoneinfoga import _parse_phoneinfoga
from weft.modules.search.searx_footprint import SearxFootprint

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, searxng=None):
    secrets = FakeSecrets({"SEARXNG_URL": searxng} if searxng else {})
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=secrets)


def _e(etype, value):
    return Entity.make(etype, value, source_module="seed", confidence=1.0, seed_id="s1")


# --- wayback ---------------------------------------------------------------

def test_wayback_parses_urls_and_historical_subdomains():
    http = FakeHttp({"web.archive.org/cdx": (200, [
        ["original", "timestamp"],
        ["http://example.com/", "20020120142510"],
        ["http://old.example.com/login", "20100901045957"],
        ["http://example.com/page", "20150101000000"],
    ])})
    out = asyncio.run(Wayback().run(_e(EntityType.DOMAIN, "example.com"), _ctx(http)))
    urls = {e.value for e in out if e.type is EntityType.URL}
    subs = {e.value for e in out if e.type is EntityType.DOMAIN}
    assert "http://example.com" in urls  # URL normalisation strips the trailing slash
    assert "old.example.com" in subs            # historical subdomain recovered
    assert all(e.metadata.get("archived") or e.metadata.get("historical") for e in out)


def test_wayback_header_row_skipped():
    http = FakeHttp({"web.archive.org/cdx": (200, [["original", "timestamp"]])})
    assert asyncio.run(Wayback().run(_e(EntityType.DOMAIN, "example.com"), _ctx(http))) == []


# --- search_footprint (SearXNG) --------------------------------------------

def test_searx_footprint_parses_results():
    # results are kept only if they actually mention the seed ("Robert Huzo")
    http = FakeHttp({"/search": (200, {"results": [
        {"url": "https://a.example/1", "title": "Robert Huzo on LinkedIn", "engine": "google"},
        {"url": "https://b.example/2", "title": "profile", "content": "robert huzo, security", "engine": "bing"},
        {"url": "https://a.example/1", "title": "dup Robert Huzo", "engine": "ddg"},  # dedup
    ]})})
    out = asyncio.run(SearxFootprint().run(_e(EntityType.NAME, "Robert Huzo"), _ctx(http, searxng="http://sx:8080")))
    assert {e.value for e in out} == {"https://a.example/1", "https://b.example/2"}
    assert all(e.type is EntityType.URL for e in out)


def test_searx_footprint_drops_irrelevant_fuzzy_hits():
    # a search engine can fuzzy-rank a page that never mentions the seed (e.g. "Hürzeler" for
    # "Robert Huzo") — it must be dropped so it does not poison later reasoning.
    http = FakeHttp({"/search": (200, {"results": [
        {"url": "https://bbc.co.uk/sport/hurzeler-signs", "title": "Hurzeler signs new deal",
         "content": "Brighton manager", "engine": "google"},
        {"url": "https://real.example/robert-huzo", "title": "Robert Huzo", "engine": "bing"},
    ]})})
    out = asyncio.run(SearxFootprint().run(_e(EntityType.NAME, "Robert Huzo"), _ctx(http, searxng="http://sx:8080")))
    assert {e.value for e in out} == {"https://real.example/robert-huzo"}   # Hurzeler dropped


def test_searx_health_down_when_unreachable():
    h = asyncio.run(SearxFootprint().health(_ctx(FakeHttp({"/search": (502, None)}), searxng="http://sx:8080")))
    assert not h.ok and "not reachable" in h.detail


def test_searx_health_up_when_reachable():
    h = asyncio.run(SearxFootprint().health(_ctx(FakeHttp({"/search": (200, {"results": []})}), searxng="http://sx:8080")))
    assert h.ok


# --- phoneinfoga parser ----------------------------------------------------

def test_phoneinfoga_parser_extracts_urls():
    sample = (
        "Results for +441234567890\n"
        "Google: https://www.google.com/search?q=%22%2B44...%22\n"
        "Social: https://twitter.com/search?q=441234567890.\n"
        "dup https://twitter.com/search?q=441234567890\n"
    )
    out = _parse_phoneinfoga(sample)
    assert "https://www.google.com/search?q=%22%2B44...%22" in out
    assert out.count("https://twitter.com/search?q=441234567890") == 1  # trailing '.' stripped + deduped


def test_registry_discovers_phase4_modules():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {"wayback", "search_footprint", "phoneinfoga"} <= names
