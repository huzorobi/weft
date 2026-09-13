"""Subdomain discovery from crt.sh certificate transparency.

crt.sh returns a JSON array of certificate rows; ``name_value`` is a newline-separated
list of names that may include wildcards (``*.example.com``) and the apex. We split,
strip wildcards, drop the seed itself, dedup, and emit each as a DOMAIN entity.

crt.sh is reliable but flaky on the first hit; the shared HTTP client retries a
non-JSON body, so a single transient empty response does not look like "no subdomains".
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

CRTSH_URL = "https://crt.sh/"


@register
class CrtSh(Module):
    name = "crtsh"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.9
    timeout_s = 45

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(CRTSH_URL, params={"q": f"%.{entity.value}", "output": "json"})
        if status != 200 or not isinstance(data, list):
            return []
        names: set[str] = set()
        for row in data:
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lstrip("*.").lower()
                if name and name != entity.value and name.endswith(entity.value):
                    names.add(name)
        return [
            Entity.make(EntityType.DOMAIN, n, source_module=self.name,
                        confidence=self.reliability, seed_id=entity.seed_id,
                        metadata={"discovered_via": "crt.sh CT logs"})
            for n in sorted(names)
        ]
