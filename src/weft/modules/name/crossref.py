"""Academic and publication footprint via Crossref (free, keyless, passive).

Crossref indexes scholarly works and their metadata. Searching a person or organisation
surfaces publications associated with the query — each a DOI link with title, publisher, and
date. Useful for building a subject's public/academic footprint. Keyless, passive.

Publication matches are query-based (a shared name is not proof of authorship), so results
carry modest confidence.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

WORKS = "https://api.crossref.org/works"
MAX_WORKS = 10


@register
class Crossref(Module):
    name = "crossref"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.URL]
    access = Access.FREE_API
    reliability = 0.45   # query match, not confirmed authorship
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            WORKS, params={"query": entity.value, "rows": str(MAX_WORKS)})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    for work in (data.get("message", {}) or {}).get("items", [])[:MAX_WORKS]:
        doi = work.get("DOI")
        if not doi or doi in seen:
            continue
        seen.add(doi)
        title = (work.get("title") or [None])[0]
        year = None
        parts = (work.get("published", {}) or {}).get("date-parts") or work.get("issued", {}).get("date-parts")
        if parts and parts[0]:
            year = parts[0][0]
        out.append(Entity.make(EntityType.URL, f"https://doi.org/{doi}", source_module=source,
                               confidence=reliability, seed_id=seed.seed_id, label="publication",
                               metadata={k: v for k, v in {
                                   "title": title,
                                   "publisher": work.get("publisher"),
                                   "type": work.get("type"),
                                   "year": year,
                                   "matches": seed.value,
                               }.items() if v}))
    return out
