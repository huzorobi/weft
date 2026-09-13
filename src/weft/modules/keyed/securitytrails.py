"""Subdomain history via SecurityTrails (free key, passive).

SecurityTrails keeps historical DNS data; its subdomain endpoint returns known subdomains of a
domain, including ones no longer live — a wider net than current-state sources. Free tier is
~50 queries/month. Self-disables without a key.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.keyed import KeyedApiModule
from weft.core.registry import register

SUBDOMAINS = "https://api.securitytrails.com/v1/domain/{domain}/subdomains"
MAX_SUBDOMAINS = 250


@register
class SecurityTrails(KeyedApiModule):
    name = "securitytrails"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    secret_env = "SECURITYTRAILS_API_KEY"
    reliability = 0.8
    timeout_s = 30

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        headers = self._key_header(ctx, "APIKEY")
        if ctx.http is None or headers is None:
            return []
        status, data = await ctx.http.get_json(
            SUBDOMAINS.format(domain=entity.value), params={"children_only": "false"}, headers=headers)
        if status != 200 or not isinstance(data, dict):
            return []
        out: list[Entity] = []
        seen: set[str] = set()
        for label in (data.get("subdomains", []) or [])[:MAX_SUBDOMAINS]:
            fqdn = f"{str(label).strip().lower()}.{entity.value}".rstrip(".")
            if fqdn and fqdn not in seen:
                seen.add(fqdn)
                out.append(Entity.make(EntityType.DOMAIN, fqdn, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"discovered_via": "SecurityTrails (historical DNS)",
                                                 "parent": entity.value}))
        return out
