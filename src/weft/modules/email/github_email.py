"""GitHub accounts tied to an email, via commit search.

Searches commits by author email and yields the author's GitHub login and the
repositories touched. Commit search by email is inherently partial (many commits use
private or noreply addresses), so findings get modest confidence. Requires a free
token: the search API is unusable unauthenticated.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register
from weft.modules.github_common import GITHUB_API, gh_headers


@register
class GithubEmail(Module):
    name = "github_email"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.USERNAME, EntityType.URL, EntityType.NAME]
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
            f"{GITHUB_API}/search/commits",
            params={"q": f"author-email:{entity.value}", "per_page": 30},
            headers=gh_headers(token),
        )
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_commits(data, entity, self.name, self.reliability)


def _parse_commits(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_login: set[str] = set()
    seen_repo: set[str] = set()
    for item in data.get("items", []) or []:
        author = item.get("author") or {}
        login = author.get("login")
        if login and login not in seen_login:
            seen_login.add(login)
            out.append(Entity.make(EntityType.USERNAME, login, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"service": "github"}))
        repo = (item.get("repository") or {}).get("html_url")
        if repo and repo not in seen_repo:
            seen_repo.add(repo)
            out.append(Entity.make(EntityType.URL, repo, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"role": "repo_contributed"}))
        name = ((item.get("commit") or {}).get("author") or {}).get("name")
        if name:
            out.append(Entity.make(EntityType.NAME, name, source_module=source,
                                   confidence=reliability * 0.9, seed_id=seed.seed_id))
    return out
