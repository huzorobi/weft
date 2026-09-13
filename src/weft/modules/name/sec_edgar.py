"""US corporate filings via SEC EDGAR full-text search (free, keyless).

Searches the SEC's EDGAR full-text index for a name or company and returns the entities
that filed — company names and their CIK. Complements the UK-only Companies House and the
global GLEIF with the US registry. Free and keyless; the SEC requires a descriptive
User-Agent (Weft's HTTP client sets one).
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"


@register
class SecEdgar(Module):
    name = "sec_edgar"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.6   # full-text search is fuzzy
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(EDGAR_FTS, params={"q": f'"{entity.value}"'})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float, *, cap: int = 10) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    for hit in (data.get("hits", {}) or {}).get("hits", [])[:cap]:
        for name in (hit.get("_source", {}) or {}).get("display_names", []) or []:
            company = str(name).split("  (")[0].strip()      # "Acme Inc  (ACME) (CIK 0001234)" -> "Acme Inc"
            cik = None
            if "CIK " in name:
                cik = name.split("CIK ")[-1].rstrip(") ").strip()
            if company and company.lower() not in seen:
                seen.add(company.lower())
                out.append(Entity.make(EntityType.ORGANISATION, company, source_module=source,
                                       confidence=reliability, seed_id=seed.seed_id,
                                       metadata={"cik": cik, "registry": "SEC EDGAR (US)"}))
    return out
