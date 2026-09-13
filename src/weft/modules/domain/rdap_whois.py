"""Registration data via RDAP (the structured successor to WHOIS).

Queries ``rdap.org``, which bootstraps to the authoritative registry (following the
redirect). Extracts registration/expiry/update dates and status as metadata on the
domain, nameservers as DOMAIN entities, and the registrant organisation as an
ORGANISATION entity where it is public. Registrant details are frequently redacted
for privacy; when they are, we record that fact rather than inventing a registrant.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

RDAP_URL = "https://rdap.org/domain/"


@register
class RdapWhois(Module):
    name = "rdap_whois"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN, EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.9
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        status, data = await ctx.http.get_json(RDAP_URL + entity.value)
        if status != 200 or not isinstance(data, dict):
            return []

        out: list[Entity] = []
        dates = {e.get("eventAction"): e.get("eventDate")
                 for e in data.get("events", []) if isinstance(e, dict)}
        meta = {
            "registration_events": {k: v for k, v in dates.items() if k},
            "status": data.get("status", []),
        }
        registrant = _registrant_org(data)
        if registrant:
            meta["registrant"] = registrant
            out.append(Entity.make(
                EntityType.ORGANISATION, registrant, source_module=self.name,
                confidence=0.7, seed_id=entity.seed_id, metadata={"role": "registrant"},
            ))
        else:
            meta["registrant"] = "redacted or not public"

        # domain node enrichment
        out.append(Entity(
            type=EntityType.DOMAIN, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id, metadata=meta,
        ))
        # nameservers
        for ns in data.get("nameservers", []) or []:
            host = (ns.get("ldhName") if isinstance(ns, dict) else None)
            if host:
                out.append(Entity.make(
                    EntityType.DOMAIN, host.rstrip("."), source_module=self.name,
                    confidence=self.reliability, seed_id=entity.seed_id,
                    metadata={"record": "ns"},
                ))
        return out


def _registrant_org(data: dict) -> str | None:
    """Pull a registrant organisation name from RDAP entities where public."""
    for ent in data.get("entities", []) or []:
        roles = ent.get("roles", []) if isinstance(ent, dict) else []
        if "registrant" not in roles:
            continue
        vcard = ent.get("vcardArray")
        if not (isinstance(vcard, list) and len(vcard) == 2):
            continue
        for field in vcard[1]:
            # vCard field: [name, params, type, value]
            if isinstance(field, list) and len(field) >= 4 and field[0] in ("org", "fn"):
                val = field[3]
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return None
