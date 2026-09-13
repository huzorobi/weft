"""Cryptographic identity proofs from Keybase (free, keyless).

Keybase links a username to verified social proofs — a Twitter, GitHub, Reddit, or
Hacker News account the person cryptographically proved they control. That verification
makes it a high-confidence identity pivot for entity resolution. Free and keyless.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

LOOKUP = "https://keybase.io/_/api/1.0/user/lookup.json"


@register
class Keybase(Module):
    name = "keybase"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.USERNAME, EntityType.URL]
    access = Access.FREE_API
    reliability = 0.8   # proofs are cryptographically verified
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(LOOKUP, params={"usernames": entity.value})
        if status != 200 or not isinstance(data, dict):
            return []
        them = data.get("them") or []
        if not them or not them[0]:
            return []
        return _parse(them[0], entity, self.name, self.reliability)


def _parse(user: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    basics = user.get("basics", {}) or {}
    kb_user = basics.get("username")
    if kb_user:
        out.append(Entity.make(EntityType.URL, f"https://keybase.io/{kb_user}", source_module=source,
                               confidence=reliability, seed_id=seed.seed_id, metadata={"role": "keybase_profile"}))
    for p in (user.get("proofs_summary", {}) or {}).get("all", []) or []:
        url = p.get("service_url") or p.get("proof_url")
        service = p.get("proof_type")
        nametag = p.get("nametag")
        if url:
            out.append(Entity.make(EntityType.SOCIAL_PROFILE, url, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"service": service, "verified": True}, label=service))
        if nametag and nametag.lower() != seed.value.lower():
            out.append(Entity.make(EntityType.USERNAME, nametag, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"service": service, "verified": True}))
    return out
