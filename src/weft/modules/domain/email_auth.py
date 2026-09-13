"""Email spoofability verdict from SPF and DMARC (offline DNS).

Reads a domain's SPF and DMARC policy from DNS TXT records and judges whether the domain
can be spoofed — a high-signal, passive check that needs only DNS. A domain with no DMARC,
or DMARC ``p=none``, can usually be spoofed in a phishing email; ``p=reject`` with a strict
SPF is protected. The verdict is deterministic and recorded on the domain node.
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
class EmailAuth(Module):
    name = "email_auth"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.DOMAIN]
    access = Access.OFFLINE
    reliability = 0.9
    timeout_s = 20

    async def health(self, ctx=None):
        return HealthStatus.up() if _HAVE else HealthStatus.down("dnspython not installed")

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if not _HAVE:
            return []
        spf = next((t for t in self._txt(entity.value) if t.lower().startswith("v=spf1")), None)
        dmarc = next((t for t in self._txt(f"_dmarc.{entity.value}") if t.lower().startswith("v=dmarc1")), None)
        verdict, reasons = spoofability(spf, dmarc)
        return [Entity(
            type=EntityType.DOMAIN, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id,
            metadata={"spf": spf, "dmarc": dmarc, "spoofability": verdict, "spoof_reasons": reasons},
            label=f"spoofability: {verdict}",
        )]

    def _txt(self, name: str) -> list[str]:
        try:
            answers = dns.resolver.resolve(name, "TXT", lifetime=8.0)
        except Exception:
            return []
        return [b"".join(a.strings).decode("utf-8", "replace") for a in answers]


def spoofability(spf: str | None, dmarc: str | None) -> tuple[str, list[str]]:
    """Return ('spoofable'|'partial'|'protected', reasons) from SPF and DMARC policy."""
    reasons: list[str] = []

    spf_all = None
    if not spf:
        reasons.append("no SPF record")
    else:
        low = spf.lower()
        if "-all" in low:
            spf_all = "hard"
        elif "~all" in low:
            spf_all = "soft"
            reasons.append("SPF uses softfail (~all)")
        elif "+all" in low or "all" not in low:
            spf_all = "open"
            reasons.append("SPF is permissive (+all or no 'all')")

    dmarc_p = None
    if not dmarc:
        reasons.append("no DMARC record")
    else:
        for part in dmarc.split(";"):
            part = part.strip().lower()
            if part.startswith("p="):
                dmarc_p = part[2:].strip()
        if dmarc_p == "none":
            reasons.append("DMARC policy p=none (monitor only, not enforced)")
        elif dmarc_p == "quarantine":
            reasons.append("DMARC policy p=quarantine")

    protected = (dmarc_p == "reject" and spf_all == "hard")
    enforced = dmarc_p in ("reject", "quarantine")
    if protected:
        return "protected", reasons or ["DMARC p=reject with strict SPF"]
    if (not dmarc) or dmarc_p == "none":
        return "spoofable", reasons
    if enforced:
        return "partial", reasons
    return "spoofable", reasons
