"""North-American IP registration via ARIN RDAP (free, keyless, passive).

RIPEstat covers RIPE (Europe/Middle East) space; this covers ARIN (North America) — the
registrant organisation, network name, CIDR and abuse contact behind a US/Canada address.
RDAP is the IETF-standard successor to whois; ARIN serves it keyless. Passive read.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

ARIN_RDAP = "https://rdap.arin.net/registry/ip/"


@register
class ArinRdap(Module):
    name = "arin_rdap"
    accepts = [EntityType.IP]
    produces = [EntityType.ORGANISATION, EntityType.EMAIL]
    access = Access.FREE_API
    reliability = 0.85
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(f"{ARIN_RDAP}{entity.value}")
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _vcard(entity: dict) -> dict:
    """Flatten an RDAP entity's jCard into {property: value} (fn, email, org, ...)."""
    out: dict[str, str] = {}
    for item in (entity.get("vcardArray", [None, []])[1] or []):
        if isinstance(item, list) and len(item) >= 4 and item[0] not in out:
            out[item[0]] = item[3]
    return out


def _cidr(data: dict) -> str | None:
    for c in data.get("cidr0_cidrs", []) or []:
        if c.get("v4prefix"):
            return f"{c['v4prefix']}/{c.get('length')}"
        if c.get("v6prefix"):
            return f"{c['v6prefix']}/{c.get('length')}"
    return None


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    base_meta = {
        "network_name": data.get("name"),
        "handle": data.get("handle"),
        "cidr": _cidr(data),
        "allocation_type": data.get("type"),
        "registry": "ARIN",
        "for_ip": seed.value,
    }
    seen_emails: set[str] = set()
    for ent in data.get("entities", []) or []:
        roles = ent.get("roles", []) or []
        card = _vcard(ent)
        org = card.get("fn") or card.get("org")
        if org and "registrant" in roles:
            out.append(Entity.make(EntityType.ORGANISATION, org, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={k: v for k, v in base_meta.items() if v}))
        # abuse / technical contact emails, from this entity or its sub-entities
        for e in (ent, *(ent.get("entities", []) or [])):
            card2 = _vcard(e)
            email = card2.get("email")
            if email and "@" in email and email.lower() not in seen_emails:
                seen_emails.add(email.lower())
                role = "abuse" if "abuse" in (e.get("roles", []) or []) else "network"
                out.append(Entity.make(EntityType.EMAIL, email, source_module=source,
                                       confidence=reliability * 0.9, seed_id=seed.seed_id,
                                       metadata={"role": f"{role} contact", "for_ip": seed.value}))
    return out
