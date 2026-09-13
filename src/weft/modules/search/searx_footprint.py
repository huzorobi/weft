"""Web footprint via a self-hosted SearXNG instance.

SearXNG aggregates many search engines behind one JSON API we run ourselves, so there
is no key, no bill, and far less blocking than scraping Google directly. For a phone,
email, or name seed it returns the pages that mention it. Search hits are weak evidence
on their own (a common name matches many people), so they get low confidence and lean
on corroboration; the operator filters with the confidence slider.

The instance URL comes from the ``SEARXNG_URL`` setting (default the compose service).
If the instance is unreachable the module self-disables rather than silently returning
nothing.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

DEFAULT_SEARXNG = "http://localhost:8080"


@register
class SearxFootprint(Module):
    name = "search_footprint"
    accepts = [EntityType.PHONE, EntityType.EMAIL, EntityType.NAME, EntityType.USERNAME]
    produces = [EntityType.URL]
    access = Access.SELF_HOSTED
    reliability = 0.4
    timeout_s = 30

    def _base(self, ctx) -> str:
        url = ctx.secrets.get("SEARXNG_URL") if ctx and ctx.secrets else None
        return (url or DEFAULT_SEARXNG).rstrip("/")

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        # a reachable SearXNG returns JSON for a trivial query; otherwise self-disable
        status, _ = await ctx.http.get_json(f"{self._base(ctx)}/search",
                                            params={"q": "test", "format": "json"})
        if status != 200:
            return HealthStatus.down(f"SearXNG not reachable at {self._base(ctx)} (status {status})")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            f"{self._base(ctx)}/search", params={"q": entity.value, "format": "json"})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse_results(data, entity, self.name, self.reliability)


def _seed_tokens(value: str) -> list[str]:
    return [t for t in value.lower().replace(",", " ").split() if len(t) >= 3]


def _relevant(result: dict, seed_value: str, tokens: list[str]) -> bool:
    """Keep a result only if it actually mentions the seed — search engines fuzzy-rank, so a
    query for 'Robert Huzo' can return pages that never contain 'huzo' (a poison for later
    reasoning). Require the whole seed, or all of its significant tokens, in the text/url."""
    hay = " ".join(str(result.get(k, "")) for k in ("title", "content", "url")).lower()
    if seed_value.lower() in hay:
        return True
    return bool(tokens) and all(t in hay for t in tokens)


def _parse_results(data: dict, seed: Entity, source: str, reliability: float, *, cap: int = 25) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    tokens = _seed_tokens(seed.value)
    for r in (data.get("results") or []):
        url = r.get("url")
        if not url or url in seen or not _relevant(r, seed.value, tokens):
            continue
        seen.add(url)
        out.append(Entity.make(EntityType.URL, url, source_module=source,
                               confidence=reliability, seed_id=seed.seed_id,
                               metadata={"title": r.get("title"), "engine": r.get("engine"),
                                         "mentions": seed.value}))
        if len(out) >= cap:
            break
    return out
