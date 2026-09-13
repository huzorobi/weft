"""urlscan.io + AlienVault OTX (mocked HTTP + fake key); self-disable without key."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.otx import Otx
from weft.modules.domain.urlscan import UrlScan

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, keys=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=FakeSecrets(keys or {}))


def _seed():
    return Entity.make(EntityType.DOMAIN, "example.com", source_module="seed", confidence=1.0, seed_id="s")


# --- OTX ---
def test_otx_disabled_without_key():
    h = asyncio.run(Otx().health(_ctx(FakeHttp({}))))
    assert not h.ok and "free key" in h.detail


def test_otx_passive_dns_parse():
    http = FakeHttp({"passive_dns": (200, {"passive_dns": [
        {"hostname": "api.example.com", "address": "1.2.3.4"},
        {"hostname": "other.net", "address": "5.6.7.8"},         # off-domain host excluded; ip kept
    ]})})
    out = asyncio.run(Otx().run(_seed(), _ctx(http, {"OTX_API_KEY": "k"})))
    doms = {e.value for e in out if e.type is EntityType.DOMAIN}
    ips = {e.value for e in out if e.type is EntityType.IP}
    assert "api.example.com" in doms and "other.net" not in doms
    assert "1.2.3.4" in ips


# --- urlscan ---
def test_urlscan_disabled_without_key():
    h = asyncio.run(UrlScan().health(_ctx(FakeHttp({}))))
    assert not h.ok and "free key" in h.detail


def test_urlscan_search_parse():
    http = FakeHttp({"urlscan.io/api/v1/search": (200, {"results": [
        {"page": {"domain": "sub.example.com", "url": "https://sub.example.com/x", "ip": "9.9.9.9"}},
        {"page": {"domain": "example.com", "url": "https://example.com/", "ip": "9.9.9.9"}},
    ]})})
    out = asyncio.run(UrlScan().run(_seed(), _ctx(http, {"URLSCAN_API_KEY": "k"})))
    by = {}
    for e in out:
        by.setdefault(e.type, set()).add(e.value)
    assert "sub.example.com" in by.get(EntityType.DOMAIN, set())
    assert "https://sub.example.com/x" in by.get(EntityType.URL, set())
    assert "9.9.9.9" in by.get(EntityType.IP, set())


def test_registry_discovers_infra_modules():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {"otx", "urlscan"} <= names
