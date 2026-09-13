"""Legal-entity lookup via the GLEIF LEI API (free, keyless).

GLEIF is the global registry of Legal Entity Identifiers. A name search returns matching
organisations with their registered address and LEI — a clean, worldwide corporate-identity
source that complements the UK-only Companies House. Free and keyless (open data).
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

LEI_RECORDS = "https://api.gleif.org/api/v1/lei-records"


@register
class Gleif(Module):
    name = "gleif"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.ORGANISATION, EntityType.ADDRESS]
    access = Access.FREE_API
    reliability = 0.7
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            LEI_RECORDS, params={"filter[entity.legalName]": entity.value, "page[size]": 5})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    for rec in data.get("data", []) or []:
        attrs = rec.get("attributes", {}) or {}
        ent = attrs.get("entity", {}) or {}
        name = (ent.get("legalName", {}) or {}).get("name")
        if not name:
            continue
        out.append(Entity.make(EntityType.ORGANISATION, name, source_module=source,
                               confidence=reliability, seed_id=seed.seed_id,
                               metadata={"lei": attrs.get("lei"), "status": ent.get("status"),
                                         "jurisdiction": ent.get("jurisdiction")}))
        addr = ent.get("legalAddress", {}) or {}
        parts = [str(x) for x in (addr.get("addressLines") or [])]
        parts += [str(addr[k]) for k in ("city", "region", "country", "postalCode") if addr.get(k)]
        line = ", ".join(p for p in parts if p)
        if line:
            out.append(Entity.make(EntityType.ADDRESS, line, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"role": "registered_office", "for": name}))
    return out
