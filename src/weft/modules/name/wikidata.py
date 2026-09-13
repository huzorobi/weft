"""Structured identity via Wikidata (free, keyless).

For a notable person or organisation, Wikidata anchors the name to a structured entity and
its declared links — official website, GitHub, and other external identifiers — giving a
high-quality pivot. Two keyless calls: search for the entity, then read its claims.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

API = "https://www.wikidata.org/w/api.php"

# claim property -> (entity type, URL template or None for a plain string)
_CLAIMS = {
    "P856": (EntityType.URL, "{}"),                       # official website
    "P2037": (EntityType.SOCIAL_PROFILE, "https://github.com/{}"),
    "P553": (EntityType.SOCIAL_PROFILE, None),            # website account on (rarely useful) -> skip URL build
}


@register
class Wikidata(Module):
    name = "wikidata"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.PERSON, EntityType.URL, EntityType.SOCIAL_PROFILE]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(API, params={
            "action": "wbsearchentities", "search": entity.value, "language": "en",
            "format": "json", "limit": 1})
        if status != 200 or not isinstance(data, dict) or not data.get("search"):
            return []
        hit = data["search"][0]
        qid = hit.get("id")
        out: list[Entity] = [Entity.make(
            EntityType.PERSON, hit.get("label", entity.value), source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id,
            metadata={"wikidata_id": qid, "description": hit.get("description"),
                      "wikidata_url": hit.get("concepturi")})]
        if hit.get("concepturi"):
            out.append(Entity.make(EntityType.URL, hit["concepturi"], source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id,
                                   metadata={"role": "wikidata_entity"}))
        if qid:
            out.extend(await self._claims(qid, entity, ctx))
        return out

    async def _claims(self, qid, seed, ctx) -> list[Entity]:
        status, data = await ctx.http.get_json(API, params={
            "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"})
        if status != 200 or not isinstance(data, dict):
            return []
        claims = (((data.get("entities") or {}).get(qid) or {}).get("claims")) or {}
        out: list[Entity] = []
        for prop, (etype, tmpl) in _CLAIMS.items():
            if tmpl is None:
                continue
            for c in claims.get(prop, []) or []:
                val = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
                if isinstance(val, str) and val:
                    out.append(Entity.make(etype, tmpl.format(val), source_module=self.name,
                                           confidence=self.reliability, seed_id=seed.seed_id,
                                           metadata={"wikidata_property": prop}))
        return out
