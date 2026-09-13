"""Domain footprint via theHarvester (external OSINT binary).

Runs theHarvester over free, keyless passive sources and parses its JSON output into
EMAIL, DOMAIN, and IP entities. theHarvester is an external binary: if it is not on
PATH the base ``health()`` check (``requires_binary``) reports the module down and the
orchestrator skips it for the whole run, so its absence is visible, not a silent zero.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register

# Keyless passive sources only (no free-key or paid source requested).
SOURCES = "crtsh,certspotter,rapiddns,hackertarget,anubis,otx,duckduckgo"


@register
class TheHarvester(Module):
    name = "theharvester"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.EMAIL, EntityType.DOMAIN, EntityType.IP]
    access = Access.OFFLINE
    reliability = 0.6
    requires_binary = "theHarvester"
    timeout_s = 300

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        with tempfile.TemporaryDirectory(prefix="weft-harvester-") as tmp:
            out_base = os.path.join(tmp, "out")
            cmd = ["theHarvester", "-d", entity.value, "-b", SOURCES, "-f", out_base]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s - 5)
            except (asyncio.TimeoutError, FileNotFoundError):
                return []

            data = self._read_json(out_base)
            if not data:
                return []

        out: list[Entity] = []
        for email in _as_list(data.get("emails")):
            out.append(Entity.make(EntityType.EMAIL, email, source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id))
        for host in _as_list(data.get("hosts")):
            name = str(host).split(":", 1)[0].strip().lower()
            if name and name != entity.value and name.endswith(entity.value):
                out.append(Entity.make(EntityType.DOMAIN, name, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id))
            # host lines are sometimes "name:ip"
            if ":" in str(host):
                ip = str(host).split(":", 1)[1].strip()
                if ip:
                    out.append(Entity.make(EntityType.IP, ip, source_module=self.name,
                                           confidence=self.reliability, seed_id=entity.seed_id))
        for ip in _as_list(data.get("ips")):
            out.append(Entity.make(EntityType.IP, str(ip), source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id))
        return out

    @staticmethod
    def _read_json(out_base: str) -> dict | None:
        for path in (out_base + ".json", out_base):
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        return json.load(fh)
                except Exception:
                    return None
        return None


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
