"""Historical URLs from the Common Crawl index (free, keyless).

Common Crawl is a large open web corpus. Its CDX index returns every URL it has crawled
under a domain — a second historical-URL source alongside the Wayback Machine, often
surfacing endpoints Wayback missed. Keyless and open (commercial-clean).
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

COLLINFO = "https://index.commoncrawl.org/collinfo.json"


@register
class CommonCrawl(Module):
    name = "commoncrawl"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.URL, EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.7
    timeout_s = 45

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, indexes = await ctx.http.get_json(COLLINFO)
        if status != 200 or not isinstance(indexes, list) or not indexes:
            return []
        cdx = indexes[0].get("cdx-api")
        if not cdx:
            return []
        status, text = await ctx.http.get_text(
            cdx, params={"url": f"{entity.value}/*", "output": "json", "limit": 300})
        if status != 200 or not text:
            return []
        return _parse_cdx(text, entity, self.name, self.reliability)


def _parse_cdx(text: str, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_url: set[str] = set()
    seen_host: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        url = rec.get("url")
        if not url or url in seen_url:
            continue
        seen_url.add(url)
        out.append(Entity.make(EntityType.URL, url, source_module=source, confidence=reliability,
                               seed_id=seed.seed_id,
                               metadata={"discovered_via": "Common Crawl", "timestamp": rec.get("timestamp"),
                                         "status": rec.get("status")}))
        host = (urlsplit(url).hostname or "").lower().lstrip(".")
        if host and host != seed.value and host.endswith(seed.value) and host not in seen_host:
            seen_host.add(host)
            out.append(Entity.make(EntityType.DOMAIN, host, source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata={"discovered_via": "Common Crawl"}))
    return out
