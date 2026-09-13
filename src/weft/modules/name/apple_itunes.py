"""Published mobile/desktop apps via the iTunes/App Store search API (free, keyless, passive).

Searches the App Store for software and keeps the results whose seller matches the query — so
an organisation seed yields the apps it publishes, each an App Store link, plus the seller as a
confirmed organisation and the bundle identifier. Keyless, passive.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

SEARCH = "https://itunes.apple.com/search"
MAX_APPS = 15


@register
class AppleItunes(Module):
    name = "apple_itunes"
    accepts = [EntityType.ORGANISATION, EntityType.NAME]
    produces = [EntityType.URL, EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.6
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            SEARCH, params={"term": entity.value, "entity": "software", "limit": str(MAX_APPS)})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _relevant(seller: str, artist: str, query: str) -> bool:
    """Keep only results whose seller/developer plausibly matches the query — the term search
    returns loose matches (searching one brand can surface a rival), so filter by seller."""
    q = query.lower()
    tokens = [t for t in q.replace(",", " ").split() if len(t) >= 4]
    hay = f"{seller} {artist}".lower()
    return q in hay or any(t in hay for t in tokens)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_sellers: set[str] = set()
    for app in data.get("results", [])[:MAX_APPS]:
        seller = app.get("sellerName") or app.get("artistName") or ""
        artist = app.get("artistName") or ""
        if not _relevant(seller, artist, seed.value):
            continue
        url = app.get("trackViewUrl")
        if url:
            out.append(Entity.make(EntityType.URL, url, source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, label="app",
                                   metadata={k: v for k, v in {
                                       "app_name": app.get("trackName"),
                                       "seller": seller,
                                       "bundle_id": app.get("bundleId"),
                                       "genre": app.get("primaryGenreName"),
                                   }.items() if v}))
        if seller and seller.lower() not in seen_sellers:
            seen_sellers.add(seller.lower())
            out.append(Entity.make(EntityType.ORGANISATION, seller, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"role": "app publisher"}))
    return out
