"""UK directorships via the Companies House public API (free key).

Given a name, search the officer index, then for the closest matches pull their
appointments to yield the companies they are officers of and the registered office
addresses. Authentication is HTTP Basic with the free API key as the username and an
empty password.

Name search is inherently fuzzy (many officers share a name), so officer matches get
moderate confidence; a company reached through a confirmed officer's appointments gets
higher confidence. Calls are bounded (top matches, capped appointments) to respect the
free-tier rate limit.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

BASE = "https://api.company-information.service.gov.uk"
MAX_OFFICERS = 3
MAX_APPOINTMENTS = 25


@register
class CompaniesHouse(Module):
    name = "companies_house"
    accepts = [EntityType.NAME, EntityType.PERSON]
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

        status, data = await ctx.http.get_json(
            f"{BASE}/search/officers", params={"q": entity.value, "items_per_page": 20}, auth=auth,
        )
        if status != 200 or not isinstance(data, dict):
            return []

        out: list[Entity] = []
        items = data.get("items", []) or []
        for officer in items[:MAX_OFFICERS]:
            self_link = (officer.get("links", {}) or {}).get("self", "")
            person_meta = {
                "appointment_count": officer.get("appointment_count"),
                "date_of_birth": officer.get("date_of_birth"),
                "address": officer.get("address_snippet"),
                "description": officer.get("description"),
            }
            person = Entity.make(
                EntityType.PERSON, officer.get("title", entity.value), source_module=self.name,
                confidence=0.6, seed_id=entity.seed_id,
                metadata={k: v for k, v in person_meta.items() if v},
            )
            out.append(person)
            if officer.get("address_snippet"):
                out.append(Entity.make(
                    EntityType.ADDRESS, officer["address_snippet"], source_module=self.name,
                    confidence=0.6, seed_id=entity.seed_id, metadata={"role": "officer_correspondence"},
                ))
            out.extend(await self._appointments(self_link, entity, ctx, auth))
        return out

    async def _appointments(self, self_link, seed, ctx, auth) -> list[Entity]:
        if not self_link:
            return []
        path = self_link if self_link.endswith("/appointments") else self_link.rstrip("/") + "/appointments"
        status, data = await ctx.http.get_json(f"{BASE}{path}", auth=auth)
        if status != 200 or not isinstance(data, dict):
            return []
        out: list[Entity] = []
        for appt in (data.get("items", []) or [])[:MAX_APPOINTMENTS]:
            company = appt.get("appointed_to", {}) or {}
            name = company.get("company_name")
            if name:
                out.append(Entity.make(
                    EntityType.ORGANISATION, name, source_module=self.name, confidence=0.8,
                    seed_id=seed.seed_id,
                    metadata={
                        "company_number": company.get("company_number"),
                        "officer_role": appt.get("officer_role"),
                        "appointed_on": appt.get("appointed_on"),
                    },
                ))
            addr = appt.get("address")
            if isinstance(addr, dict):
                line = ", ".join(str(addr[k]) for k in
                                 ("premises", "address_line_1", "locality", "postal_code") if addr.get(k))
                if line:
                    out.append(Entity.make(
                        EntityType.ADDRESS, line, source_module=self.name, confidence=0.75,
                        seed_id=seed.seed_id, metadata={"role": "registered_office"},
                    ))
        return out
