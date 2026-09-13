"""Reverse-IP and subdomain pivots via HackerTarget (free, keyless, passive).

Two high-value pivots from HackerTarget's public API (keyless, ~50 queries/day):
  - reverse IP: an IP -> the other domains hosted on it (co-hosting / shared infrastructure);
  - host search: a domain -> its subdomains and their IPs.
HackerTarget performs the lookup against its own data; Weft only reads the result, so this is
passive from the target's point of view.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

REVERSE_IP = "https://api.hackertarget.com/reverseiplookup/"
HOST_SEARCH = "https://api.hackertarget.com/hostsearch/"
MAX_RESULTS = 200
# HackerTarget signals problems in the body, not the status code.
_ERRORS = ("API count exceeded", "error", "No DNS", "no records", "invalid")


def _is_error(text: str) -> bool:
    low = (text or "").strip().lower()
    return not low or any(e.lower() in low for e in _ERRORS)


def _clean_domain(host: str) -> str | None:
    h = (host or "").strip().lower().rstrip(".")
    if not h or "." not in h or h.endswith(".arpa") or " " in h:
        return None
    return h


@register
class HackerTarget(Module):
    name = "hackertarget"
    accepts = [EntityType.IP, EntityType.DOMAIN]
    produces = [EntityType.DOMAIN, EntityType.IP]
    access = Access.FREE_API
    reliability = 0.7   # co-hosting is a lead; shared IPs can be CDN/parking
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        if entity.type is EntityType.IP:
            return await self._reverse_ip(entity, ctx)
        return await self._host_search(entity, ctx)

    async def _reverse_ip(self, entity, ctx) -> list[Entity]:
        status, text = await ctx.http.get_text(REVERSE_IP, params={"q": entity.value})
        if status != 200 or _is_error(text):
            return []
        out: list[Entity] = []
        seen: set[str] = set()
        for line in text.splitlines()[:MAX_RESULTS]:
            d = _clean_domain(line)
            if d and d not in seen:
                seen.add(d)
                out.append(Entity.make(EntityType.DOMAIN, d, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"discovered_via": "reverse IP (co-hosted)", "on_ip": entity.value}))
        return out

    async def _host_search(self, entity, ctx) -> list[Entity]:
        status, text = await ctx.http.get_text(HOST_SEARCH, params={"q": entity.value})
        if status != 200 or _is_error(text):
            return []
        out: list[Entity] = []
        seen_hosts: set[str] = set()
        for line in text.splitlines()[:MAX_RESULTS]:
            host, _, ip = line.partition(",")
            d = _clean_domain(host)
            if d and d not in seen_hosts:
                seen_hosts.add(d)
                out.append(Entity.make(EntityType.DOMAIN, d, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"discovered_via": "hostsearch (subdomain)", "of": entity.value}))
            ip = ip.strip()
            if ip and _looks_ipv4(ip):
                out.append(Entity.make(EntityType.IP, ip, source_module=self.name,
                                       confidence=self.reliability, seed_id=entity.seed_id,
                                       metadata={"resolves": d} if d else {}))
        return out


def _looks_ipv4(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
