"""Network intelligence from RIPEstat (free, keyless, open data).

RIPE NCC's open data API. For an IP it returns the abuse contact and the network holder —
the accountable party behind an address. Authoritative and fully open (commercial use
permitted), no key.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

ABUSE = "https://stat.ripe.net/data/abuse-contact-finder/data.json"
NETINFO = "https://stat.ripe.net/data/network-info/data.json"


@register
class RipeStat(Module):
    name = "ripestat"
    accepts = [EntityType.IP]
    produces = [EntityType.EMAIL, EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.8
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        out: list[Entity] = []
        status, data = await ctx.http.get_json(ABUSE, params={"resource": entity.value})
        if status == 200 and isinstance(data, dict):
            for email in (data.get("data", {}) or {}).get("abuse_contacts", []) or []:
                out.append(Entity.make(EntityType.EMAIL, email, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"role": "network abuse contact", "for_ip": entity.value}))
        status, data = await ctx.http.get_json(NETINFO, params={"resource": entity.value})
        if status == 200 and isinstance(data, dict):
            asns = (data.get("data", {}) or {}).get("asns", []) or []
            prefix = (data.get("data", {}) or {}).get("prefix")
            if asns:
                out.append(Entity.make(EntityType.ORGANISATION, f"AS{asns[0]}", source_module=self.name,
                                       confidence=self.reliability * 0.8, seed_id=entity.seed_id,
                                       metadata={"role": "announcing ASN", "prefix": prefix}))
        return out
