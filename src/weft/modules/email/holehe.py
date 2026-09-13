"""Which sites have an account for an email, via holehe (external tool).

holehe checks an email against many sites. It is an external binary: absent from
PATH, the base health check disables it. It probes third-party sites, so it is
ToS-flagged and off unless the operator opts in. Each site with an account becomes a
SOCIAL_PROFILE entity.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register


@register
class Holehe(Module):
    name = "holehe"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.SOCIAL_PROFILE]
    access = Access.OFFLINE
    requires_binary = "holehe"
    tos_risk = True
    reliability = 0.6
    timeout_s = 180

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        cmd = ["holehe", entity.value, "--only-used", "--no-color"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s - 5)
        except (asyncio.TimeoutError, FileNotFoundError):
            return []
        sites = _parse_holehe(out.decode("utf-8", "replace"))
        return [
            Entity.make(EntityType.SOCIAL_PROFILE, f"{site} ({entity.value})", source_module=self.name,
                        confidence=self.reliability, seed_id=entity.seed_id,
                        metadata={"service": site, "email": entity.value}, label=site)
            for site in sites
        ]


def _parse_holehe(stdout: str) -> list[str]:
    """Return the site names holehe marked as used (``[+]`` lines)."""
    sites: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("[+]"):
            token = line[3:].strip().split()[0] if line[3:].strip() else ""
            if token:
                sites.append(token)
    return sites
