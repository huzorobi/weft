"""Public code and config on GitHub referencing a domain.

Uses the code search API to find repositories whose code mentions the domain, a
common source of leaked config, internal hostnames, and contact addresses. Code
search requires authentication, so this needs a free token.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register
from weft.modules.github_common import GITHUB_API, gh_headers


@register
class GithubDomain(Module):
    name = "github_domain"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.URL]
    access = Access.FREE_API
    requires_free_key = True
    secret_env = "GITHUB_TOKEN"
    reliability = 0.6
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        token = ctx.secrets.get(self.secret_env) if ctx.secrets else None
        if not token:
            return HealthStatus.down(f"missing free key ({self.secret_env}); module disables itself")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        token = ctx.secrets.get(self.secret_env) if ctx.secrets else None
        if ctx.http is None or not token:
            return []
        status, data = await ctx.http.get_json(
            f"{GITHUB_API}/search/code",
            params={"q": entity.value, "per_page": 30},
            headers=gh_headers(token),
        )
        if status != 200 or not isinstance(data, dict):
            return []
        out: list[Entity] = []
        seen: set[str] = set()
        for item in data.get("items", []) or []:
            url = item.get("html_url")
            repo = (item.get("repository") or {}).get("full_name")
            if url and url not in seen:
                seen.add(url)
                out.append(Entity.make(EntityType.URL, url, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"repo": repo, "role": "code_reference"}))
        return out
