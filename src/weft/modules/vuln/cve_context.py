"""CVE context from CISA KEV + OSV.dev (free, keyless, passive).

Given a CVE (e.g. surfaced by Shodan InternetDB for an IP), this adds the context that decides
whether it matters: is it in CISA's Known Exploited Vulnerabilities catalogue (actively
exploited in the wild, and is it used by ransomware), and what does OSV.dev say (summary and
severity). Both sources are open and keyless. The KEV catalogue is cached once per run.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
OSV_VULN = "https://api.osv.dev/v1/vulns/"


@register
class CveContext(Module):
    name = "cve_context"
    accepts = [EntityType.CVE]
    produces = [EntityType.CVE]
    access = Access.FREE_API
    reliability = 0.9   # authoritative catalogues
    timeout_s = 45

    def __init__(self) -> None:
        self._kev: dict[str, dict] | None = None
        self._lock: asyncio.Lock | None = None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def _kev_catalog(self, ctx) -> dict[str, dict]:
        if self._kev is not None:
            return self._kev
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._kev is not None:
                return self._kev
            catalog: dict[str, dict] = {}
            status, data = await ctx.http.get_json(KEV_URL)
            if status == 200 and isinstance(data, dict):
                for v in data.get("vulnerabilities", []) or []:
                    cid = v.get("cveID")
                    if cid:
                        catalog[cid.upper()] = v
            self._kev = catalog
            return catalog

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        cve = entity.value.upper()
        if not cve.startswith("CVE-"):
            return []
        meta: dict = {}
        kev = (await self._kev_catalog(ctx)).get(cve)
        if kev:
            meta.update({
                "known_exploited": True,
                "kev_name": kev.get("vulnerabilityName"),
                "kev_date_added": kev.get("dateAdded"),
                "kev_due_date": kev.get("dueDate"),
                "ransomware_use": kev.get("knownRansomwareCampaignUse"),
            })
        else:
            meta["known_exploited"] = False
        osv = await self._osv(cve, ctx)
        if osv:
            meta.update(osv)
        if len(meta) == 1 and meta.get("known_exploited") is False:
            return []   # nothing to add beyond "not in KEV"
        return [Entity(type=EntityType.CVE, value=cve, source_module=self.name,
                       confidence=self.reliability, seed_id=entity.seed_id, metadata=meta,
                       label="known-exploited" if meta.get("known_exploited") else "CVE context")]

    async def _osv(self, cve: str, ctx) -> dict:
        status, data = await ctx.http.get_json(f"{OSV_VULN}{cve}")
        if status != 200 or not isinstance(data, dict):
            return {}
        out: dict = {}
        if data.get("summary"):
            out["osv_summary"] = data["summary"]
        elif data.get("details"):
            out["osv_summary"] = str(data["details"])[:200]
        severities = [s.get("score") for s in (data.get("severity") or []) if s.get("score")]
        if severities:
            out["severity"] = severities[0]
        aliases = [a for a in (data.get("aliases") or []) if a != cve]
        if aliases:
            out["aliases"] = aliases[:5]
        return out
