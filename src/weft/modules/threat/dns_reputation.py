"""Domain reputation via public malware-filtering DNS resolvers (free, keyless, passive).

Malware-filtering resolvers (Cloudflare Family, AdGuard) return a null answer for domains
they consider malicious. This module resolves a domain at a neutral resolver (Google) and at
each filter: if the neutral resolver returns a real address but a filter blocks it, that
filter has flagged the domain. Passive — it queries public resolvers over DNS-over-HTTPS,
never the domain itself. Keyless.

A filter block is a useful signal, not proof (filters over-block), so a flag carries moderate
confidence and names which providers blocked it.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

NEUTRAL = ("google", "https://dns.google/resolve", None)
FILTERS = [
    ("cloudflare_family", "https://family.cloudflare-dns.com/dns-query", {"Accept": "application/dns-json"}),
    ("adguard", "https://dns.adguard-dns.com/resolve", None),
]
_NULL_IPS = {"0.0.0.0", "::", "127.0.0.1"}
_A = 1  # DNS A record type


async def _a_records(ctx, url, headers, domain) -> tuple[int | None, list[str]]:
    status, data = await ctx.http.get_json(url, params={"name": domain, "type": "A"}, headers=headers)
    if status != 200 or not isinstance(data, dict):
        return None, []
    answers = [a.get("data") for a in (data.get("Answer") or []) if a.get("type") == _A]
    return data.get("Status"), [a for a in answers if a]


def _is_blocked(rcode: int | None, answers: list[str]) -> bool:
    if rcode == 3:                       # NXDOMAIN from a filter = blocked
        return True
    if not answers:                      # no A record at all
        return True
    return all(a in _NULL_IPS for a in answers)   # sinkholed to 0.0.0.0 etc.


@register
class DnsReputation(Module):
    name = "dns_reputation"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    access = Access.FREE_API
    reliability = 0.6
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        _, neutral = await _a_records(ctx, NEUTRAL[1], NEUTRAL[2], entity.value)
        real = [a for a in neutral if a not in _NULL_IPS]
        if not real:
            return []   # neutral has no real address to contrast against — cannot assess
        blocked_by: list[str] = []
        for fname, furl, fheaders in FILTERS:
            frcode, fans = await _a_records(ctx, furl, fheaders, entity.value)
            if frcode is None and not fans:
                continue   # filter did not answer — do not infer a block from an error
            if _is_blocked(frcode, fans):
                blocked_by.append(fname)
        if not blocked_by:
            return []
        conf = min(self.reliability + 0.1 * (len(blocked_by) - 1), 0.85)
        return [Entity(
            type=EntityType.DOMAIN, value=entity.value, source_module=self.name,
            confidence=conf, seed_id=entity.seed_id,
            metadata={"reputation": "flagged", "blocked_by": blocked_by,
                      "neutral_resolves_to": real[:3],
                      "note": "blocked by malware-filtering DNS; a lead, not proof"},
            label="flagged (DNS filter)",
        )]
