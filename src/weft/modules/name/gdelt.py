"""Global news mentions via the GDELT DOC 2.0 API (free, keyless, passive).

GDELT indexes worldwide news in near real time. Given a name, organisation, or domain, this
returns recent articles that mention it — each a URL with its source, date, country, and
language. Useful for surfacing public reporting on a subject. Keyless, passive.

News-source domains are recorded in article metadata rather than emitted as pivotable domains,
to keep the graph from expanding into every news outlet.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_ARTICLES = 25
TIMESPAN = "3m"   # look back 3 months; without a window GDELT returns few or no results


@register
class Gdelt(Module):
    name = "gdelt"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION, EntityType.DOMAIN]
    produces = [EntityType.URL]
    access = Access.FREE_API
    reliability = 0.55   # a news mention; common names are ambiguous
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        query = f'domain:{entity.value}' if entity.type is EntityType.DOMAIN else _phrase(entity.value)
        status, data = await ctx.http.get_json(DOC_API, params={
            "query": query, "mode": "artlist", "format": "json",
            "maxrecords": str(MAX_ARTICLES), "sort": "datedesc", "timespan": TIMESPAN,
        })
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _phrase(value: str) -> str:
    v = value.strip()
    return f'"{v}"' if " " in v else v


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    for art in (data.get("articles", []) or [])[:MAX_ARTICLES]:
        url = art.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(Entity.make(EntityType.URL, url, source_module=source, confidence=reliability,
                               seed_id=seed.seed_id, label="news article",
                               metadata={k: v for k, v in {
                                   "title": art.get("title"),
                                   "news_source": art.get("domain"),
                                   "seen_date": art.get("seendate"),
                                   "source_country": art.get("sourcecountry"),
                                   "language": art.get("language"),
                                   "mentions": seed.value,
                               }.items() if v}))
    return out
