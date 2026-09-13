"""Native username checker — no external binary (inspired by Obipixel's socialFIND).

Checks a handle across many sites from a JSON site list (WhatsMyName-style), using Weft's
own async HTTP client and rate limiter, so username enumeration works even when maigret and
sherlock are not installed. Given a USERNAME it checks that handle directly; given a NAME it
generates candidate handles (firstlast, first.last, flast, ...) and checks each — name-derived
hits are low-confidence leads, flagged as candidates.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register
from weft.core.username_gen import candidates_from_name

_SITES_FILE = Path(__file__).with_name("username_sites.json")
_MAX_NAME_CANDIDATES = 6
_CONCURRENCY = 10


def _load_sites() -> list[dict]:
    try:
        return json.loads(_SITES_FILE.read_text(encoding="utf-8")).get("sites", [])
    except Exception:
        return []


@register
class UsernameCheck(Module):
    name = "username_check"
    accepts = [EntityType.USERNAME, EntityType.NAME]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.USERNAME]
    access = Access.FREE_API
    tos_risk = True
    reliability = 0.6
    timeout_s = 90

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        if not _load_sites():
            return HealthStatus.down("username_sites.json missing or empty")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        sites = _load_sites()
        if not sites:
            return []

        if entity.type is EntityType.USERNAME:
            return await self._check_handle(entity.value, sites, ctx, entity, derived=False)

        # NAME -> candidate handles (low-confidence leads)
        out: list[Entity] = []
        for cand in candidates_from_name(entity.value, cap=_MAX_NAME_CANDIDATES):
            out.extend(await self._check_handle(cand, sites, ctx, entity, derived=True))
        return out

    async def _check_handle(self, handle: str, sites, ctx, seed: Entity, *, derived: bool) -> list[Entity]:
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def one(site):
            async with sem:
                return site, await _site_hit(ctx.http, site, handle)

        results = await asyncio.gather(*(one(s) for s in sites), return_exceptions=True)
        conf = (self.reliability * 0.55) if derived else self.reliability
        out: list[Entity] = []
        hit_any = False
        for r in results:
            if isinstance(r, Exception):
                continue
            site, url = r
            if not url:
                continue
            hit_any = True
            md = {"service": site.get("name"), "handle": handle}
            if derived:
                md["candidate"] = True
                md["derived_from_name"] = seed.value
            out.append(Entity.make(EntityType.SOCIAL_PROFILE, url, source_module=self.name,
                                   confidence=conf, seed_id=seed.seed_id, metadata=md, label=site.get("name")))
        if hit_any and derived:
            # surface the confirmed candidate handle as a (low-confidence) USERNAME entity
            out.append(Entity.make(EntityType.USERNAME, handle, source_module=self.name,
                                   confidence=conf, seed_id=seed.seed_id,
                                   metadata={"candidate": True, "derived_from_name": seed.value}))
        return out


async def _site_hit(http, site: dict, username: str) -> str | None:
    """Return the profile URL if the username exists on the site, else None."""
    if "." in username and site.get("no_period"):
        return None
    url = site["url"].format(username)
    try:
        status, text = await http.get_text(url)
    except Exception:
        return None
    if status != site.get("e_code", 200):
        return None
    e_string = site.get("e_string")
    if e_string and e_string not in text:
        return None
    m_string = site.get("m_string")
    if m_string and m_string in text:
        return None
    return url
