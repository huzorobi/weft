"""Hacker News profile via the public Firebase API (free, keyless, passive).

Resolves a username to its Hacker News profile — karma, account age, and the "about" text,
which frequently carries a personal site, email, or other handles. Those links are extracted
as their own entities. Public read, keyless, passive.
"""
from __future__ import annotations

import html
import re

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

USER_API = "https://hacker-news.firebaseio.com/v0/user/"
PROFILE = "https://news.ycombinator.com/user?id="
_HREF = re.compile(r'href="([^"]+)"', re.I)
_URL = re.compile(r'https?://[^\s"<>]+', re.I)


@register
class HackerNews(Module):
    name = "hackernews"
    accepts = [EntityType.USERNAME]
    produces = [EntityType.SOCIAL_PROFILE, EntityType.URL]
    access = Access.FREE_API
    reliability = 0.7
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(f"{USER_API}{entity.value}.json")
        if status != 200 or not isinstance(data, dict) or not data.get("id"):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _parse(user: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    uid = user.get("id")
    out: list[Entity] = [Entity.make(
        EntityType.SOCIAL_PROFILE, f"{PROFILE}{uid}", source_module=source, confidence=reliability,
        seed_id=seed.seed_id, label="hacker news",
        metadata={k: v for k, v in {
            "platform": "hacker_news", "karma": user.get("karma"),
            "created": user.get("created"), "submissions": len(user.get("submitted") or []),
        }.items() if v is not None})]
    about = html.unescape(user.get("about") or "")
    links = set(_HREF.findall(about)) | set(_URL.findall(about))
    for link in links:
        link = html.unescape(link).strip().rstrip('".,)')
        if link.startswith("http"):
            out.append(Entity.make(EntityType.URL, link, source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata={"discovered_via": "HN profile about"}))
    return out
