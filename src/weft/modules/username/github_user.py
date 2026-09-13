"""GitHub user profile from a username.

Uses the public user API. Works without a token (60 requests/hour); a free token
raises the limit and is used when present. Yields the public profile fields as linked
entities: name, public email, blog URL, company, location, and Twitter handle.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register
from weft.modules.github_common import GITHUB_API, gh_headers


@register
class GithubUser(Module):
    name = "github_user"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.NAME, EntityType.EMAIL, EntityType.URL,
                EntityType.ORGANISATION, EntityType.USERNAME]
    access = Access.FREE_API
    secret_env = "GITHUB_TOKEN"     # optional here; raises the rate limit
    reliability = 0.9
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        token = ctx.secrets.get(self.secret_env) if ctx.secrets else None
        status, data = await ctx.http.get_json(
            f"{GITHUB_API}/users/{entity.value}", headers=gh_headers(token))
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_user(data, entity, self.name, self.reliability)


def _parse_user(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []

    def add(etype, value, conf=reliability, **md):
        if value:
            out.append(Entity.make(etype, str(value), source_module=source,
                                   confidence=conf, seed_id=seed.seed_id, metadata=md or None))

    add(EntityType.NAME, data.get("name"))
    add(EntityType.EMAIL, data.get("email"))
    add(EntityType.URL, data.get("html_url"), role="github_profile")
    add(EntityType.URL, data.get("blog"), role="blog")
    add(EntityType.ORGANISATION, data.get("company"))
    if data.get("twitter_username"):
        add(EntityType.USERNAME, data["twitter_username"], reliability * 0.9, service="twitter")
    return out
