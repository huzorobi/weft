"""SPF/DMARC spoofability + Common Crawl."""
from __future__ import annotations

import asyncio
import json

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.commoncrawl import CommonCrawl, _parse_cdx
from weft.modules.domain.email_auth import EmailAuth, spoofability

from _fakes import FakeHttp


def _dom(v="example.com"):
    return Entity.make(EntityType.DOMAIN, v, source_module="seed", confidence=1.0, seed_id="s")


# --- spoofability verdicts ---
def test_spoofability_verdicts():
    assert spoofability(None, None)[0] == "spoofable"
    assert spoofability("v=spf1 -all", "v=DMARC1; p=reject")[0] == "protected"
    assert spoofability("v=spf1 ~all", "v=DMARC1; p=none")[0] == "spoofable"
    assert spoofability("v=spf1 -all", "v=DMARC1; p=quarantine")[0] == "partial"
    assert spoofability("v=spf1 include:x -all", None)[0] == "spoofable"   # SPF but no DMARC


def test_email_auth_enriches_domain():
    class Stub(EmailAuth):
        def _txt(self, name):
            if name.startswith("_dmarc."):
                return ["v=DMARC1; p=reject; rua=mailto:x"]
            return ["v=spf1 include:_spf.google.com -all"]
    out = asyncio.run(Stub().run(_dom(), RunContext(engagement_id="e", operator="r", allow_tos_risk=False, depth=0)))
    md = out[0].metadata
    assert md["spoofability"] == "protected"
    assert md["spf"].startswith("v=spf1") and md["dmarc"].startswith("v=DMARC1")


# --- common crawl ---
def test_parse_cdx():
    text = "\n".join(json.dumps(x) for x in [
        {"url": "https://example.com/", "timestamp": "20260807", "status": "200"},
        {"url": "https://api.example.com/v1", "timestamp": "20260808", "status": "200"},
        {"url": "https://example.com/", "timestamp": "20260809"},   # dup url
    ])
    out = _parse_cdx(text, _dom(), "commoncrawl", 0.7)
    urls = {e.value for e in out if e.type is EntityType.URL}
    doms = {e.value for e in out if e.type is EntityType.DOMAIN}
    assert "https://api.example.com/v1" in urls
    assert "api.example.com" in doms
    assert len([e for e in out if e.value == "https://example.com"]) == 1   # deduped (trailing slash normalised)


def test_commoncrawl_run_two_step(monkeypatch):
    jsonl = json.dumps({"url": "https://sub.example.com/x", "timestamp": "2026", "status": "200"})
    http = FakeHttp({
        "collinfo.json": (200, [{"cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-34-index"}]),
        "CC-MAIN-2026-34-index": (200, jsonl),
    })
    ctx = RunContext(engagement_id="e", operator="r", allow_tos_risk=False, depth=0, http=http)
    out = asyncio.run(CommonCrawl().run(_dom(), ctx))
    assert any(e.value == "https://sub.example.com/x" for e in out)


def test_registry_discovers_domain_extra():
    from weft.core import registry
    registry.discover()
    assert {"email_auth", "commoncrawl"} <= set(registry.registered_classes())
