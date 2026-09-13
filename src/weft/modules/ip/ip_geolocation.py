"""Free IP geolocation via ip-api.com (no key), inspired by Obipixel's traceVIEW.

Enriches each IP entity with country, city, coordinates, ISP, and ASN, and surfaces the
owning organisation as an ORGANISATION entity. The coordinates feed the KML map export.
ip-api's free tier is keyless and rate-limited (45 requests/minute), so the orchestrator's
per-module limiter keeps us under it.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

IPAPI = "http://ip-api.com/json/"
_FIELDS = "status,message,country,countryCode,regionName,city,lat,lon,isp,org,as,query"


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
        status, data = await ctx.http.get_json(f"{IPAPI}{entity.value}", params={"fields": _FIELDS})
        if status != 200 or not isinstance(data, dict) or data.get("status") != "success":
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    meta = {
        "country": data.get("country"), "country_code": data.get("countryCode"),
        "region": data.get("regionName"), "city": data.get("city"),
        "lat": data.get("lat"), "lon": data.get("lon"),
        "isp": data.get("isp"), "org": data.get("org"), "asn": data.get("as"),
    }
    meta = {k: v for k, v in meta.items() if v not in (None, "")}
    label = ", ".join(x for x in (data.get("city"), data.get("country")) if x) or None

    out = [Entity(
        type=EntityType.IP, value=seed.value, source_module=source,
        confidence=reliability, seed_id=seed.seed_id, metadata=meta, label=label,
    )]
    owner = data.get("org") or data.get("isp")
    if owner:
        out.append(Entity.make(EntityType.ORGANISATION, owner, source_module=source,
                               confidence=reliability * 0.9, seed_id=seed.seed_id,
                               metadata={"role": "ip_owner", "asn": data.get("as")}))
    return out
