"""Dark-web (Ahmia) parse + double-gating + Tor self-disable; XposedOrNot breach check."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module, RunContext
from weft.modules.darkweb.ahmia_tor import DarkWebAhmia, _parse_ahmia
from weft.modules.email.xposedornot import XposedOrNot

from _fakes import FakeHttp

_AHMIA_HTML = '''
<li class="result">
  <h4><a href="/search/redirect?redirect_url=http%3A%2F%2Fabcdefghij234567.onion%2Fp">Example Market</a></h4>
  <cite>http://abcdefghij234567.onion/p</cite>
  <p>a page mentioning the target</p>
</li>
<li class="result">
  <h4><a href="/search/redirect?redirect_url=http%3A%2F%2Fqrstuvwxyz234567.onion%2F">Second Site</a></h4>
  <cite>http://qrstuvwxyz234567.onion/</cite>
</li>
'''


def _e(etype=EntityType.DOMAIN, v="example.com"):
    return Entity.make(etype, v, source_module="seed", confidence=1.0, seed_id="s")


def test_parse_ahmia_extracts_onions_and_titles():
    out = _parse_ahmia(_AHMIA_HTML)
    urls = {u for u, _ in out}
    titles = {t for _, t in out}
    assert "http://abcdefghij234567.onion/p" in urls
    assert "http://qrstuvwxyz234567.onion/" in urls
    assert "Example Market" in titles


def test_parse_ahmia_excludes_ahmia_itself():
    html = '<li class="result"><cite>http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/</cite></li>'
    assert _parse_ahmia(html) == []


def test_dark_web_double_gated():
    m = DarkWebAhmia()
    e = _e()
    assert m.dark_web is True
    assert not m.can_run(e, allow_tos_risk=True, allow_dark_web=False)   # dark-web gate closed
    assert m.can_run(e, allow_tos_risk=True, allow_dark_web=True)        # opened by the toggle


def test_normal_module_unaffected_by_dark_web_flag():
    class Plain(Module):
        name = "plain"; accepts = [EntityType.DOMAIN]; produces = []; access = Access.OFFLINE
        async def run(self, entity, ctx): return []
    assert Plain().can_run(_e(), allow_tos_risk=False, allow_dark_web=False)


def test_dark_web_health_self_disables_without_tor():
    import os
    os.environ["DARKWEB_TOR_PROXY"] = "socks5://127.0.0.1:1"   # nothing listening
    try:
        h = asyncio.run(DarkWebAhmia().health())
        assert not h.ok and "Tor" in h.detail
    finally:
        del os.environ["DARKWEB_TOR_PROXY"]


def test_xposedornot_parses_breaches():
    http = FakeHttp({"xposedornot.com": (200, {"breaches": [["Dropbox", "Twitter", "LinkedIn"]]})})
    ctx = RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)
    out = asyncio.run(XposedOrNot().run(_e(EntityType.EMAIL, "rob@example.com"), ctx))
    vals = {e.value for e in out}
    assert vals == {"Dropbox", "Twitter", "LinkedIn"}
    assert all(e.type is EntityType.BREACH for e in out)


def test_registry_discovers_darkweb_and_xposedornot():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {"darkweb_ahmia", "xposedornot"} <= names
