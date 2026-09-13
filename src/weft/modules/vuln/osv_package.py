"""Known vulnerabilities in a software package via OSV.dev (free, keyless, passive).

Given a package (as produced by the npm module, e.g. ``npm:lodash``), this queries OSV.dev for
the vulnerabilities affecting it and emits each as a CVE entity plus an advisory link — so a
developer's published packages chain through to the CVEs against them, which the ``cve_context``
module then enriches with CISA KEV. Keyless, passive (POST query to OSV).
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

QUERY = "https://api.osv.dev/v1/query"
ADVISORY = "https://osv.dev/vulnerability/"
MAX_VULNS = 30


@register
class OsvPackage(Module):
    name = "osv_package"
    accepts = [EntityType.PACKAGE]
    produces = [EntityType.CVE, EntityType.URL]
    access = Access.FREE_API
    reliability = 0.85
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        ecosystem, _, name = entity.value.partition(":")
        # OSV ecosystem names are capitalised (npm, PyPI, Go, ...); npm stays lowercase
        eco = {"pypi": "PyPI", "npm": "npm", "go": "Go", "crates.io": "crates.io",
               "rubygems": "RubyGems", "maven": "Maven", "nuget": "NuGet"}.get(ecosystem.lower(), ecosystem)
        if not name:
            return []
        status, data = await ctx.http.post_json(
            QUERY, json={"package": {"name": name, "ecosystem": eco}})
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    seen_cve: set[str] = set()
    for vuln in (data.get("vulns", []) or [])[:MAX_VULNS]:
        vid = vuln.get("id")
        summary = vuln.get("summary") or (str(vuln.get("details", ""))[:160] or None)
        if vid:
            out.append(Entity.make(EntityType.URL, f"{ADVISORY}{vid}", source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id, label="advisory",
                                   metadata={k: v for k, v in {
                                       "advisory_id": vid, "summary": summary, "affects": seed.value,
                                   }.items() if v}))
        for alias in [vid, *(vuln.get("aliases") or [])]:
            a = str(alias or "").upper()
            if a.startswith("CVE-") and a not in seen_cve:
                seen_cve.add(a)
                out.append(Entity.make(EntityType.CVE, a, source_module=source, confidence=reliability,
                                       seed_id=seed.seed_id,
                                       metadata={"affects_package": seed.value, "summary": summary}))
    return out
