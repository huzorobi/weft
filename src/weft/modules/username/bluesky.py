"""Bluesky / AT Protocol public profiles (free, keyless, passive).

Bluesky's public API exposes profiles without authentication. Given a handle it resolves the
profile directly; given a plain username or a name it searches for matching accounts. Each
result is a decentralised social identity (handle + DID) and a strong pivot. Public read only
— no login, no private data, ToS-clean. Keyless.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

GET_PROFILE = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
SEARCH_ACTORS = "https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors"
MAX_SEARCH = 5


@register
class Bluesky(Module):
    name = "bluesky"
    accepts = [EntityType.USERNAME, EntityType.NAME, EntityType.PERSON]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.USERNAME, EntityType.URL]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        # A handle (has a dot, e.g. alice.bsky.social) resolves directly and confidently;
        # a plain username or a name is searched instead, yielding candidates.
        if entity.type is EntityType.USERNAME and "." in entity.value:
            status, data = await ctx.http.get_json(GET_PROFILE, params={"actor": entity.value})
            if status == 200 and isinstance(data, dict) and data.get("handle"):
                return _profile_entities(data, entity, self.name, self.reliability, exact=True)
            return []
        status, data = await ctx.http.get_json(SEARCH_ACTORS, params={"q": entity.value, "limit": str(MAX_SEARCH)})
        if status != 200 or not isinstance(data, dict):
            return []
        # For a person name, keep only actors matching ALL name tokens — the search returns any
        # loose match (e.g. every "Robert"), which is noise for a full name.
        strict = entity.type in (EntityType.NAME, EntityType.PERSON)
        tokens = [t for t in entity.value.lower().split() if len(t) >= 3]
        out: list[Entity] = []
        for actor in (data.get("actors", []) or [])[:MAX_SEARCH]:
            if strict and tokens:
                hay = f"{actor.get('displayName', '')} {actor.get('handle', '')}".lower()
                if not all(t in hay for t in tokens):
                    continue
            out += _profile_entities(actor, entity, self.name, 0.5, exact=False)
        return out


def _profile_entities(actor: dict, seed: Entity, source: str, confidence: float, *, exact: bool) -> list[Entity]:
    handle = actor.get("handle")
    if not handle:
        return []
    md = {k: v for k, v in {
        "did": actor.get("did"),
        "display_name": actor.get("displayName"),
        "description": actor.get("description"),
        "followers": actor.get("followersCount"),
        "match": "exact" if exact else "name_search",
    }.items() if v is not None}
    out = [
        Entity.make(EntityType.SOCIAL_PROFILE, f"https://bsky.app/profile/{handle}", source_module=source,
                    confidence=confidence, seed_id=seed.seed_id, metadata={**md, "platform": "bluesky"},
                    label="bluesky"),
        Entity.make(EntityType.USERNAME, handle, source_module=source, confidence=confidence,
                    seed_id=seed.seed_id, metadata={"platform": "bluesky", "did": actor.get("did")}),
    ]
    return out
