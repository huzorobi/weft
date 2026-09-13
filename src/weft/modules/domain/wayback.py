"""Historical URLs and old subdomains from the Wayback Machine (archive.org).

The CDX API returns every archived URL under a domain as a JSON array of rows
(``[original, timestamp]``), the first row being a header. Each URL becomes a URL
entity tagged with its snapshot timestamp; hostnames under the seed domain that differ
from it become DOMAIN entities (subdomains that existed historically, a classic source
of forgotten attack surface). The CDX API is slow, so the timeout is generous.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

CDX_URL = "https://web.archive.org/cdx/search/cdx"


@register
class Wayback(Module):
    name = "wayback"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.URL, EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.8
    timeout_s = 60

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(CDX_URL, params={
            "url": entity.value, "matchType": "domain", "output": "json",
            "fl": "original,timestamp", "collapse": "urlkey", "limit": 500,
        })
        if status != 200 or not isinstance(data, list):
            return []
        return _parse_cdx(data, entity, self.name, self.reliability)


def _parse_cdx(rows: list, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_url: set[str] = set()
    seen_host: set[str] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        original, timestamp = str(row[0]), str(row[1])
        if original == "original":   # header row
            continue
        if original not in seen_url:
            seen_url.add(original)
            out.append(Entity.make(EntityType.URL, original, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"first_snapshot": timestamp, "archived": True}))
        host = (urlsplit(original).hostname or "").lower().lstrip(".")
        if host and host != seed.value and host.endswith(seed.value) and host not in seen_host:
            seen_host.add(host)
            out.append(Entity.make(EntityType.DOMAIN, host, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"discovered_via": "wayback historical", "historical": True}))
    return out
