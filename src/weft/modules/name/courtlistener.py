"""US case law via CourtListener (Free Law Project) — free, keyless (optional token), passive.

Searches CourtListener's opinion corpus for a name or organisation and returns the cases it
appears in — each a link to the case with its court and filing date. Public-domain court data.
Works keyless; an optional free API token (COURTLISTENER_API_TOKEN) raises the rate limit.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

SEARCH = "https://www.courtlistener.com/api/rest/v4/search/"
SITE = "https://www.courtlistener.com"
MAX_CASES = 15


@register
class CourtListener(Module):
    name = "courtlistener"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.URL]
    access = Access.FREE_API
    secret_env = "COURTLISTENER_API_TOKEN"   # optional — raises rate limit
    reliability = 0.6
    timeout_s = 30

    def _headers(self, ctx):
        token = ctx.secrets.get(self.secret_env) if ctx.secrets else None
        return {"Authorization": f"Token {token}"} if token else None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(
            SEARCH, params={"q": entity.value, "type": "o"}, headers=self._headers(ctx),
        )
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen: set[str] = set()
    for case in (data.get("results", []) or [])[:MAX_CASES]:
        path = case.get("absolute_url")
        if not path:
            continue
        url = path if path.startswith("http") else SITE + path
        if url in seen:
            continue
        seen.add(url)
        out.append(Entity.make(EntityType.URL, url, source_module=source, confidence=reliability,
                               seed_id=seed.seed_id, label="court case",
                               metadata={k: v for k, v in {
                                   "case_name": case.get("caseName"),
                                   "court": case.get("court"),
                                   "date_filed": case.get("dateFiled"),
                                   "docket_number": case.get("docketNumber"),
                                   "mentions": seed.value,
                               }.items() if v}))
    return out
