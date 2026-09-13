"""Subdomain discovery from Cert Spotter certificate transparency logs.

A keyless backup to crt.sh. The API returns a JSON array of issuances, each with a
``dns_names`` list. We flatten, strip wildcards, keep names under the seed domain,
dedup, and emit DOMAIN entities.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

CERTSPOTTER_URL = "https://api.certspotter.com/v1/issuances"


@register
class CertSpotter(Module):
    name = "certspotter"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.9
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            CERTSPOTTER_URL,
            params={"domain": entity.value, "include_subdomains": "true", "expand": "dns_names"},
        )
        if status != 200 or not isinstance(data, list):
            return []
        names: set[str] = set()
        for issuance in data:
            for name in issuance.get("dns_names", []) or []:
                name = str(name).strip().lstrip("*.").lower()
                if name and name != entity.value and name.endswith(entity.value):
                    names.add(name)
        return [
            Entity.make(EntityType.DOMAIN, n, source_module=self.name,
                        confidence=self.reliability, seed_id=entity.seed_id,
                        metadata={"discovered_via": "Cert Spotter CT logs"})
            for n in sorted(names)
        ]
