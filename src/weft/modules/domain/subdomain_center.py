"""Subdomain discovery via subdomain.center (free, keyless, passive).

Returns subdomains of a domain from subdomain.center's index — complements the certificate-
transparency sources (crt.sh, certspotter) and HackerTarget hostsearch with a different data
set, widening subdomain coverage. Passive (reads an index), keyless.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

API = "https://api.subdomain.center/"
MAX_SUBDOMAINS = 250


@register
class SubdomainCenter(Module):
    name = "subdomain_center"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(API, params={"domain": entity.value})
        if status != 200 or not isinstance(data, list):
            return []
        out: list[Entity] = []
        seen: set[str] = set()
        for sub in data[:MAX_SUBDOMAINS]:
            h = str(sub).strip().lower().rstrip(".")
            if h and "." in h and h != entity.value and h not in seen:
                seen.add(h)
                out.append(Entity.make(EntityType.DOMAIN, h, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"discovered_via": "subdomain.center", "parent": entity.value}))
        return out
