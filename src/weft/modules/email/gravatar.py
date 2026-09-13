"""Gravatar profile lookup from an email hash.

Gravatar exposes a public JSON profile at ``/{md5(email)}.json`` for accounts that
have one. The profile is self-asserted by its owner but the email-to-profile link is
deterministic, so it is a high-value pivot: linked social accounts, personal URLs,
and a display name. A missing gravatar (404) simply yields no entities.
"""
from __future__ import annotations

import hashlib

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register


@register
class Gravatar(Module):
    name = "gravatar"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.USERNAME, EntityType.URL, EntityType.NAME]
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
        digest = hashlib.md5(entity.value.strip().lower().encode()).hexdigest()
        status, data = await ctx.http.get_json(f"https://www.gravatar.com/{digest}.json")
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_profile(data, entity, self.name, self.reliability)


def _parse_profile(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    entries = data.get("entry") or []
    if not entries:
        return []
    out: list[Entity] = []
    for entry in entries:
        name = entry.get("displayName")
        if name:
            out.append(Entity.make(EntityType.NAME, name, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id))
        for acct in entry.get("accounts", []) or []:
            url = acct.get("url")
            if url:
                out.append(Entity.make(EntityType.SOCIAL_PROFILE, url, source_module=source,
                                       confidence=reliability, seed_id=seed.seed_id,
                                       metadata={"service": acct.get("shortname") or acct.get("domain"),
                                                 "verified": acct.get("verified")}))
            uname = acct.get("username")
            if uname:
                out.append(Entity.make(EntityType.USERNAME, uname, source_module=source,
                                       confidence=reliability * 0.9, seed_id=seed.seed_id,
                                       metadata={"service": acct.get("shortname") or acct.get("domain")}))
        for url in entry.get("urls", []) or []:
            val = url.get("value")
            if val:
                out.append(Entity.make(EntityType.URL, val, source_module=source,
                                       confidence=reliability, seed_id=seed.seed_id,
                                       metadata={"title": url.get("title")}))
    return out
