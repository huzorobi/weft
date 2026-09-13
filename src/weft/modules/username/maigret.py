"""Social-profile discovery across many sites via maigret (external tool).

maigret checks a username against thousands of sites. It is an external binary
(disabled when absent) and ToS-flagged (off unless the operator opts in). Each claimed
profile becomes a SOCIAL_PROFILE entity, and its username a corroborating USERNAME.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register


@register
class Maigret(Module):
    name = "maigret"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.URL]
    access = Access.OFFLINE
    requires_binary = "maigret"
    tos_risk = True
    reliability = 0.6
    timeout_s = 600

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        with tempfile.TemporaryDirectory(prefix="weft-maigret-") as tmp:
            cmd = ["maigret", entity.value, "--json", "simple", "-fo", tmp,
                   "--no-progressbar", "--timeout", "15"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s - 5)
            except (asyncio.TimeoutError, FileNotFoundError):
                return []
            data = _load_report(tmp, entity.value)
        if not data:
            return []
        return _parse_maigret(data, entity, self.name, self.reliability)

    @staticmethod
    def _load_report(directory: str, username: str) -> dict | None:
        for fn in os.listdir(directory):
            if fn.endswith(".json") and username in fn and "simple" in fn:
                try:
                    with open(os.path.join(directory, fn), encoding="utf-8") as fh:
                        return json.load(fh)
                except Exception:
                    return None
        return None


def _is_claimed(record: dict) -> bool:
    status = record.get("status")
    if isinstance(status, dict):
        status = status.get("status")
    return str(status).lower() in ("claimed", "found", "yes", "true")


def _parse_maigret(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    for site, record in data.items():
        if not isinstance(record, dict) or not _is_claimed(record):
            continue
        url = record.get("url_user") or record.get("url")
        if url:
            out.append(Entity.make(EntityType.SOCIAL_PROFILE, url, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"service": site}, label=site))
    return out
