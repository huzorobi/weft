"""Pre-scanned host exposure from Shodan InternetDB (free, keyless).

InternetDB returns Shodan's already-collected view of an IP: open ports, CPEs, known
CVEs, hostnames, and tags. Because the data is pre-scanned by Shodan, reading it is
passive — Weft never touches the target. Distinct from the paid Shodan API.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

INTERNETDB = "https://internetdb.shodan.io/"


@register
class ShodanInternetDB(Module):
    name = "shodan_internetdb"
    accepts = [EntityType.IP]
    produces = [EntityType.IP, EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.8
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(f"{INTERNETDB}{entity.value}")
        if status != 200 or not isinstance(data, dict) or "ports" not in data:
            return []
        out = [Entity(
            type=EntityType.IP, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id,
            metadata={k: v for k, v in {
                "ports": data.get("ports"), "cpes": data.get("cpes"),
                "vulns": data.get("vulns"), "tags": data.get("tags"),
            }.items() if v},
        )]
        for host in data.get("hostnames", []) or []:
            h = str(host).strip().lower().rstrip(".")
            if h:
                out.append(Entity.make(EntityType.DOMAIN, h, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"discovered_via": "Shodan InternetDB (reverse DNS)"}))
        return out
