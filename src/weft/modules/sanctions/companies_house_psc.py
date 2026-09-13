"""UK beneficial ownership via Companies House PSC register (free key).

For a UK company, the Persons with Significant Control register names the people and legal
entities that ultimately own or control it — beneficial ownership, not just the officer list.
Given an ORGANISATION carrying a Companies House number (as produced by the ``companies_house``
module), this fetches its PSCs. Uses the same free Companies House key and self-disables
without it. Passive read of a public register.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

BASE = "https://api.company-information.service.gov.uk"
MAX_PSC = 25


@register
class CompaniesHousePsc(Module):
    name = "companies_house_psc"
    accepts = [EntityType.ORGANISATION]
    produces = [EntityType.PERSON, EntityType.ORGANISATION, EntityType.ADDRESS]
    access = Access.FREE_API
    requires_free_key = True
    secret_env = "COMPANIES_HOUSE_API_KEY"
    reliability = 0.85
    timeout_s = 45

    def _auth(self, ctx):
        key = ctx.secrets.get(self.secret_env) if ctx.secrets else None
        return (key, "") if key else None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        if self._auth(ctx) is None:
            return HealthStatus.down(f"missing free key ({self.secret_env}); module disables itself")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        auth = self._auth(ctx)
        if ctx.http is None or auth is None:
            return []
        number = (entity.metadata or {}).get("company_number")
        if not number:
            return []   # need a CH company number to look up PSCs — nothing to do otherwise
        status, data = await ctx.http.get_json(
            f"{BASE}/company/{number}/persons-with-significant-control", auth=auth,
        )
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, number, self.name, self.reliability)


def _parse(data: dict, seed: Entity, number: str, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    for psc in (data.get("items", []) or [])[:MAX_PSC]:
        name = psc.get("name")
        if not name:
            continue
        kind_raw = str(psc.get("kind", "")).lower()
        etype = EntityType.ORGANISATION if "legal-person" in kind_raw or "corporate" in kind_raw else EntityType.PERSON
        out.append(Entity.make(
            etype, name, source_module=source, confidence=reliability, seed_id=seed.seed_id,
            metadata={
                "role": "beneficial_owner",
                "controls_company": seed.value,
                "company_number": number,
                "natures_of_control": psc.get("natures_of_control"),
                "notified_on": psc.get("notified_on"),
                "nationality": psc.get("nationality"),
                "country_of_residence": psc.get("country_of_residence"),
            }))
        addr = psc.get("address")
        if isinstance(addr, dict):
            line = ", ".join(str(addr[k]) for k in
                             ("premises", "address_line_1", "locality", "postal_code") if addr.get(k))
            if line:
                out.append(Entity.make(
                    EntityType.ADDRESS, line, source_module=source, confidence=reliability * 0.85,
                    seed_id=seed.seed_id, metadata={"role": "psc_address", "of": name}))
    return out
