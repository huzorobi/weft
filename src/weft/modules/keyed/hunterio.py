"""Corporate email discovery via Hunter.io (free key, passive).

For a domain, Hunter.io returns the email addresses it has seen there and the organisation's
email pattern (e.g. {first}.{last}@). Free tier allows a limited number of searches per month.
Self-disables without a key.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.keyed import KeyedApiModule
from weft.core.registry import register

DOMAIN_SEARCH = "https://api.hunter.io/v2/domain-search"
MAX_EMAILS = 25


@register
class HunterIo(KeyedApiModule):
    name = "hunterio"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.EMAIL, EntityType.PERSON]
    secret_env = "HUNTERIO_API_KEY"
    reliability = 0.7
    timeout_s = 25

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        params = self._key_param(ctx, "api_key")
        if ctx.http is None or params is None:
            return []
        params["domain"] = entity.value
        status, data = await ctx.http.get_json(DOMAIN_SEARCH, params=params)
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    d = data.get("data", {}) or {}
    out: list[Entity] = []
    for rec in (d.get("emails", []) or [])[:MAX_EMAILS]:
        addr = rec.get("value")
        if not addr:
            continue
        conf = reliability * (rec.get("confidence", 80) / 100)
        out.append(Entity.make(EntityType.EMAIL, addr, source_module=source, confidence=conf,
                               seed_id=seed.seed_id,
                               metadata={k: v for k, v in {
                                   "pattern": d.get("pattern"), "type": rec.get("type"),
                                   "position": rec.get("position"), "on_domain": seed.value,
                               }.items() if v}))
        name = " ".join(x for x in (rec.get("first_name"), rec.get("last_name")) if x)
        if name:
            out.append(Entity.make(EntityType.PERSON, name, source_module=source, confidence=conf,
                                   seed_id=seed.seed_id, metadata={"email": addr, "role": rec.get("position")}))
    return out
