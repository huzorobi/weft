"""Email breach-exposure check via XposedOrNot (free, keyless).

Returns which known breaches an email address appears in — the breach-exposure signal that
was lost when Have I Been Pwned's email lookup went paid. This is a breach *check* (it
returns breach names, not dump contents); Weft never ingests or stores breach corpora.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

CHECK = "https://api.xposedornot.com/v1/check-email/"


@register
class XposedOrNot(Module):
    name = "xposedornot"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.BREACH]
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
        status, data = await ctx.http.get_json(f"{CHECK}{entity.value}")
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    names: list[str] = []
    raw = data.get("breaches")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, list):
                names.extend(str(x) for x in item)
            elif isinstance(item, str):
                names.append(item)
    out: list[Entity] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(Entity.make(EntityType.BREACH, name, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"email": seed.value, "note": "breach the address appears in"}))
    return out
