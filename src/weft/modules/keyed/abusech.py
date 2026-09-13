"""Malware / C2 infrastructure reputation via abuse.ch (free key, passive).

Checks an IP or domain against abuse.ch's ThreatFox (indicators of compromise) and URLhaus
(malware distribution URLs). A hit means the host has been seen serving or controlling malware
— a strong infrastructure-reputation signal. abuse.ch data is CC0; the API needs a free
Auth-Key (since 2024). Self-disables without the key. Uses POST (abuse.ch is POST-only).
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.keyed import KeyedApiModule
from weft.core.registry import register

THREATFOX = "https://threatfox-api.abuse.ch/api/v1/"
URLHAUS_HOST = "https://urlhaus-api.abuse.ch/v1/host/"
MAX_ITEMS = 25


@register
class AbuseCh(KeyedApiModule):
    name = "abusech"
    accepts = [EntityType.IP, EntityType.DOMAIN]
    produces = [EntityType.URL, EntityType.IP, EntityType.DOMAIN]
    secret_env = "ABUSECH_API_KEY"
    reliability = 0.85
    timeout_s = 30

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        auth = self._key_header(ctx, "Auth-Key")
        if ctx.http is None or auth is None:
            return []
        out: list[Entity] = []
        out += await self._threatfox(entity, ctx, auth)
        out += await self._urlhaus(entity, ctx, auth)
        return out

    async def _threatfox(self, entity, ctx, auth) -> list[Entity]:
        status, data = await ctx.http.post_json(
            THREATFOX, json={"query": "search_ioc", "search_term": entity.value}, headers=auth)
        if status != 200 or not isinstance(data, dict) or data.get("query_status") != "ok":
            return []
        out: list[Entity] = []
        for ioc in (data.get("data", []) or [])[:MAX_ITEMS]:
            same = Entity(type=entity.type, value=entity.value, source_module=self.name,
                          confidence=self.reliability, seed_id=entity.seed_id,
                          metadata={k: v for k, v in {
                              "reputation": "malware_ioc", "threat_type": ioc.get("threat_type"),
                              "malware": ioc.get("malware_printable"), "confidence": ioc.get("confidence_level"),
                              "first_seen": ioc.get("first_seen"), "source": "abuse.ch ThreatFox",
                          }.items() if v},
                          label="malware IOC (ThreatFox)")
            out.append(same)
        return out

    async def _urlhaus(self, entity, ctx, auth) -> list[Entity]:
        status, data = await ctx.http.post_json(
            URLHAUS_HOST, data={"host": entity.value}, headers=auth)
        if status != 200 or not isinstance(data, dict) or data.get("query_status") != "ok":
            return []
        out: list[Entity] = []
        for u in (data.get("urls", []) or [])[:MAX_ITEMS]:
            url = u.get("url")
            if url:
                out.append(Entity.make(EntityType.URL, url, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       label="malware URL",
                                       metadata={k: v for k, v in {
                                           "status": u.get("url_status"), "threat": u.get("threat"),
                                           "date_added": u.get("date_added"), "source": "abuse.ch URLhaus",
                                       }.items() if v}))
        return out
