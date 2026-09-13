"""Geocode an address via OpenStreetMap Nominatim (free, keyless).

Turns a registered-office or other address (from Companies House, GLEIF, or WHOIS) into
coordinates, so it can be placed on the KML map alongside geolocated IPs. Open data
(ODbL, commercial use permitted under the usage policy: a valid user agent and no heavy
volume). Enriches the address node in place.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

SEARCH = "https://nominatim.openstreetmap.org/search"


@register
class Nominatim(Module):
    name = "nominatim"
    accepts = [EntityType.ADDRESS]
    produces = [EntityType.ADDRESS]
    access = Access.FREE_API
    reliability = 0.6
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            SEARCH, params={"q": entity.value, "format": "jsonv2", "limit": 1})
        if status != 200 or not isinstance(data, list) or not data:
            return []
        r = data[0]
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except Exception:
            return []
        return [Entity(
            type=EntityType.ADDRESS, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id,
            metadata={"lat": lat, "lon": lon, "geocoded_name": r.get("display_name")},
            label=entity.label,
        )]
