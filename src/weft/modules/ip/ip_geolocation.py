"""IP geolocation via ipwho.is (free, keyless, commercial use permitted).

Enriches each IP entity with country, city, coordinates, ISP, and ASN, and surfaces the
owning organisation. The coordinates feed the KML map export.

Source note: ipwho.is is free and keyless and permits commercial use (unlike ip-api.com,
whose free tier is non-commercial only), which matters for a commercial engagement tool.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

IPWHO = "https://ipwho.is/"


@register
class IpGeolocation(Module):
    name = "ip_geolocation"
    accepts = [EntityType.IP]
    produces = [EntityType.IP, EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.7
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(f"{IPWHO}{entity.value}")
        if status != 200 or not isinstance(data, dict) or not data.get("success"):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    conn = data.get("connection", {}) or {}
    meta = {
        "country": data.get("country"), "country_code": data.get("country_code"),
        "region": data.get("region"), "city": data.get("city"),
        "lat": data.get("latitude"), "lon": data.get("longitude"),
        "isp": conn.get("isp"), "org": conn.get("org"),
        "asn": f"AS{conn['asn']}" if conn.get("asn") else None,
    }
    meta = {k: v for k, v in meta.items() if v not in (None, "")}
    label = ", ".join(x for x in (data.get("city"), data.get("country")) if x) or None

    out = [Entity(
        type=EntityType.IP, value=seed.value, source_module=source,
        confidence=reliability, seed_id=seed.seed_id, metadata=meta, label=label,
    )]
    owner = conn.get("org") or conn.get("isp")
    if owner:
        out.append(Entity.make(EntityType.ORGANISATION, owner, source_module=source,
                               confidence=reliability * 0.9, seed_id=seed.seed_id,
                               metadata={"role": "ip_owner", "asn": meta.get("asn")}))
    return out
