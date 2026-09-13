"""Social-profile discovery via sherlock (external tool, maigret fallback).

sherlock checks a username across many sites. External binary: disabled when absent,
ToS-flagged (off unless the operator opts in). Each found profile becomes a
SOCIAL_PROFILE entity. Parses sherlock's ``[+] Site: URL`` stdout lines.
"""
from __future__ import annotations

import asyncio
import tempfile

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register


@register
class Sherlock(Module):
    name = "sherlock"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.SOCIAL_PROFILE]
    access = Access.OFFLINE
    requires_binary = "sherlock"
    tos_risk = True
    reliability = 0.55
    timeout_s = 300

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        # Run in a temp cwd so sherlock's result file does not litter the project.
        with tempfile.TemporaryDirectory(prefix="weft-sherlock-") as tmp:
            cmd = ["sherlock", entity.value, "--print-found", "--no-color", "--timeout", "10"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, cwd=tmp, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s - 5)
            except (asyncio.TimeoutError, FileNotFoundError):
                return []
        return [
            Entity.make(EntityType.SOCIAL_PROFILE, url, source_module=self.name,
                        confidence=self.reliability, seed_id=entity.seed_id,
                        metadata={"service": site}, label=site)
            for site, url in _parse_sherlock(out.decode("utf-8", "replace"))
        ]


def _parse_sherlock(stdout: str) -> list[tuple[str, str]]:
    """Return (site, url) pairs from sherlock's ``[+] Site: URL`` lines."""
    pairs: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("[+]") and ": " in line:
            body = line[3:].strip()
            site, _, url = body.partition(": ")
            if url.startswith("http"):
                pairs.append((site.strip(), url.strip()))
    return pairs
