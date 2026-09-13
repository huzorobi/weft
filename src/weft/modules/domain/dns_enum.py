"""Offline DNS enumeration via dnspython.

Resolves A/AAAA/MX/NS/TXT for a domain. A/AAAA become IP entities; MX and NS hosts
become DOMAIN entities (worth expanding); TXT records are kept as metadata on the
domain (SPF/DMARC/verification strings), not spawned as nodes.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

try:
    import dns.resolver

    _HAVE = True
except Exception:  # pragma: no cover
    _HAVE = False


@register
class DnsEnum(Module):
    name = "dns_enum"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.IP, EntityType.DOMAIN]
    access = Access.OFFLINE
    reliability = 0.95
    timeout_s = 20

    async def health(self, ctx=None):
        return HealthStatus.up() if _HAVE else HealthStatus.down("dnspython not installed")

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if not _HAVE:
            return []
        domain = entity.value
        out: list[Entity] = []
        txt: list[str] = []

        for rtype in ("A", "AAAA"):
            for val in self._resolve(domain, rtype):
                out.append(self._mk(EntityType.IP, val, entity, note=rtype))
        for host in self._resolve(domain, "MX", mx=True):
            out.append(self._mk(EntityType.DOMAIN, host, entity, note="mx"))
        for host in self._resolve(domain, "NS"):
            out.append(self._mk(EntityType.DOMAIN, host.rstrip("."), entity, note="ns"))
        for rec in self._resolve(domain, "TXT"):
            txt.append(rec)

        if txt:
            out.append(Entity(
                type=EntityType.DOMAIN, value=domain, source_module=self.name,
                confidence=self.reliability, seed_id=entity.seed_id,
                metadata={"txt": txt},
            ))
        return out

    def _resolve(self, domain: str, rtype: str, *, mx: bool = False) -> list[str]:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=8.0)
        except Exception:
            return []
        vals = []
        for a in answers:
            if mx:
                vals.append(str(a.exchange).rstrip("."))
            elif rtype == "TXT":
                vals.append(b"".join(a.strings).decode("utf-8", "replace"))
            else:
                vals.append(str(a).rstrip("."))
        return vals

    def _mk(self, etype, value, seed, *, note):
        return Entity.make(
            etype, value, source_module=self.name, confidence=self.reliability,
            seed_id=seed.seed_id, metadata={"record": note},
        )
