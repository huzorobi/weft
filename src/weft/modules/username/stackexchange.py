"""Stack Overflow / Stack Exchange profiles (free, keyless, passive).

Searches Stack Overflow for users matching a username or name and returns their profiles — a
developer-identity pivot with reputation as a rough salience signal. Keyless (a shared daily
quota applies). Public read, passive.
"""
from __future__ import annotations

import html

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

USERS = "https://api.stackexchange.com/2.3/users"
MAX_USERS = 5


@register
class StackExchange(Module):
    name = "stackexchange"
    accepts = [EntityType.USERNAME, EntityType.NAME, EntityType.PERSON]
    produces = [EntityType.SOCIAL_PROFILE]
    access = Access.FREE_API
    reliability = 0.5   # name search returns candidates
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(USERS, params={
            "inname": entity.value, "site": "stackoverflow", "pagesize": str(MAX_USERS),
            "order": "desc", "sort": "reputation"})
        if status != 200 or not isinstance(data, dict):
            return []
        out: list[Entity] = []
        for u in (data.get("items", []) or [])[:MAX_USERS]:
            link = u.get("link")
            if not link:
                continue
            out.append(Entity.make(EntityType.SOCIAL_PROFILE, link, source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id, label="stack overflow",
                                   metadata={k: v for k, v in {
                                       "platform": "stackoverflow",
                                       "display_name": html.unescape(u.get("display_name", "")),
                                       "reputation": u.get("reputation"),
                                       "user_id": u.get("user_id"),
                                   }.items() if v not in (None, "")}))
        return out
