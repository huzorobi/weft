"""Published npm packages by a developer (free, keyless, passive).

Searches the npm registry for packages authored by a username and returns them — each a
package page, plus the source repository link (often a GitHub URL) that pivots to the
developer's code. Results are filtered to packages the username actually publishes, to keep
the fuzzy author search from adding noise. Keyless, passive.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

SEARCH = "https://registry.npmjs.org/-/v1/search"
MAX_PACKAGES = 20


@register
class Npm(Module):
    name = "npm"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.URL]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            SEARCH, params={"text": f"author:{entity.value}", "size": str(MAX_PACKAGES)})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_repos: set[str] = set()
    user = seed.value.lower()
    for obj in data.get("objects", []) or []:
        pkg = obj.get("package", {}) or {}
        publisher = (pkg.get("publisher", {}) or {}).get("username", "").lower()
        maintainers = {m.get("username", "").lower() for m in (pkg.get("maintainers") or [])}
        # keep only packages this username actually publishes/maintains
        if user != publisher and user not in maintainers:
            continue
        name = pkg.get("name")
        links = pkg.get("links", {}) or {}
        if name:
            out.append(Entity.make(EntityType.URL, links.get("npm") or f"https://www.npmjs.com/package/{name}",
                                   source_module=source, confidence=reliability, seed_id=seed.seed_id,
                                   label="npm package",
                                   metadata={k: v for k, v in {
                                       "package": name, "description": pkg.get("description"),
                                       "publisher": publisher or None,
                                   }.items() if v}))
        repo = links.get("repository")
        if repo and repo not in seen_repos:
            seen_repos.add(repo)
            out.append(Entity.make(EntityType.URL, repo, source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata={"role": "source repository", "for_package": name}))
    return out
