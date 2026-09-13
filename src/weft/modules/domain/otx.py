"""Passive DNS and related infrastructure from AlienVault OTX (free key).

OTX's passive-DNS gives the hostnames that have resolved to a domain (subdomains and
siblings) and the IPs behind them — strong infrastructure-pivot data. A free account key
is required (anonymous access is blocked), so the module self-disables without one.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

BASE = "https://otx.alienvault.com/api/v1/indicators"


@register
class Otx(Module):
    name = "otx"
    accepts = [EntityType.DOMAIN, EntityType.IP]
    produces = [EntityType.DOMAIN, EntityType.IP]
    access = Access.FREE_API
    requires_free_key = True
    secret_env = "OTX_API_KEY"
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
        kind = "IPv4" if entity.type is EntityType.IP else "domain"
        status, data = await ctx.http.get_json(f"{BASE}/{kind}/{entity.value}/passive_dns",
                                               headers={"X-OTX-API-KEY": key})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_passive_dns(data, entity, self.name, self.reliability)


def _parse_passive_dns(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    for rec in data.get("passive_dns", []) or []:
        host = str(rec.get("hostname", "")).strip().lower().rstrip(".")
        addr = str(rec.get("address", "")).strip()
        if host and host != seed.value and host.endswith(seed.value) and host not in seen:
            seen.add(host)
            out.append(Entity.make(EntityType.DOMAIN, host, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"discovered_via": "OTX passive DNS"}))
        if addr and addr not in seen and (":" in addr or addr.count(".") == 3):
            seen.add(addr)
            out.append(Entity.make(EntityType.IP, addr, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"discovered_via": "OTX passive DNS"}))
    return out
