"""Historical scans and related infrastructure from urlscan.io (free key).

urlscan's search returns every public scan touching a domain: the URLs seen, the domains
and subdomains involved, and the IPs they resolved to — a rich infrastructure-pivot source
with screenshots. A free account key is required (unauthenticated search is heavily
limited), so the module self-disables without one.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

SEARCH = "https://urlscan.io/api/v1/search/"


@register
class UrlScan(Module):
    name = "urlscan"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN, EntityType.URL, EntityType.IP]
    access = Access.FREE_API
    requires_free_key = True
    secret_env = "URLSCAN_API_KEY"
    reliability = 0.7
    timeout_s = 30

    def _key(self, ctx):
        return ctx.secrets.get(self.secret_env) if ctx.secrets else None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        if not self._key(ctx):
            return HealthStatus.down(f"missing free key ({self.secret_env}); module disables itself")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        key = self._key(ctx)
        if ctx.http is None or not key:
            return []
        status, data = await ctx.http.get_json(
            SEARCH, params={"q": f"domain:{entity.value}", "size": 100}, headers={"API-Key": key})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_search(data, entity, self.name, self.reliability)


def _parse_search(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()

    def add(etype, value, **md):
        if value and value not in seen:
            seen.add(value)
            out.append(Entity.make(etype, value, source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata=md or None))

    for r in data.get("results", []) or []:
        page = r.get("page", {}) or {}
        dom = str(page.get("domain", "")).strip().lower()
        if dom and dom != seed.value and dom.endswith(seed.value):
            add(EntityType.DOMAIN, dom, discovered_via="urlscan.io")
        add(EntityType.URL, page.get("url"), discovered_via="urlscan.io")
        ip = page.get("ip")
        if ip and (":" in str(ip) or str(ip).count(".") == 3):
            add(EntityType.IP, str(ip), discovered_via="urlscan.io")
    return out
