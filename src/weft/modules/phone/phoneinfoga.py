"""Phone footprint via PhoneInfoga (external tool), intrusive scanners off.

PhoneInfoga builds an OSINT footprint for a number: format/carrier facts and search
"dork" URLs to pivot on. It is an external binary (self-disables when absent) and is
ToS-flagged. The intrusive Truecaller-style scanner is deliberately NOT used — only the
default non-intrusive scanners run. Discovered footprint URLs become URL entities.
"""
from __future__ import annotations

import asyncio
import re

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register

_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


@register
class PhoneInfoga(Module):
    name = "phoneinfoga"
    accepts = [EntityType.PHONE]
    produces = [EntityType.URL]
    access = Access.SELF_HOSTED
    requires_binary = "phoneinfoga"
    tos_risk = True
    reliability = 0.5
    timeout_s = 120

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        # default scanners only; no intrusive/Truecaller-style scanner is requested.
        cmd = ["phoneinfoga", "scan", "-n", entity.value]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s - 5)
        except (asyncio.TimeoutError, FileNotFoundError):
            return []
        return [
            Entity.make(EntityType.URL, url, source_module=self.name,
                        confidence=self.reliability, seed_id=entity.seed_id,
                        metadata={"role": "phone_footprint_dork", "number": entity.value})
            for url in _parse_phoneinfoga(out.decode("utf-8", "replace"))
        ]


def _parse_phoneinfoga(stdout: str) -> list[str]:
    """Extract the footprint/dork URLs from PhoneInfoga output, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(stdout):
        u = m.group(0).rstrip(".,")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
