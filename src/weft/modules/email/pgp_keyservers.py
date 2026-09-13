"""Identity links from public PGP keyservers (free, keyless, passive).

A PGP key binds a person's name to one or more email addresses. Looking an email up on the
public keyservers therefore yields a real name and, crucially, the *other* emails on the same
key — a strong identity link. A hit on ProtonMail's keyserver additionally indicates a Proton
account. Reads public keyservers; passive; keyless.
"""
from __future__ import annotations

import re

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

# (label, url); ProtonMail's PKS doubles as a Proton-account signal.
KEYSERVERS = [
    ("keyserver.ubuntu.com", "https://keyserver.ubuntu.com/pks/lookup"),
    ("keys.openpgp.org", "https://keys.openpgp.org/pks/lookup"),
    ("protonmail", "https://api.protonmail.ch/pks/lookup"),
]
_UID = re.compile(r"^(?P<outside>.*?)\s*<(?P<inside>[^>]+)>\s*$")


def _looks_email(s: str) -> bool:
    return "@" in s and "." in s.split("@")[-1]


@register
class PgpKeyservers(Module):
    name = "pgp_keyservers"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.NAME, EntityType.EMAIL]
    access = Access.FREE_API
    reliability = 0.8   # a shared PGP key is a strong link
    timeout_s = 30

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        names: dict[str, set[str]] = {}     # name -> keyservers
        emails: dict[str, set[str]] = {}    # alias email -> keyservers
        proton = False
        for label, url in KEYSERVERS:
            status, text = await ctx.http.get_text(
                url, params={"op": "index", "options": "mr", "search": entity.value})
            if status != 200 or not text or "info:" not in text:
                continue
            if label == "protonmail":
                proton = True
            for name, email in _parse_uids(text):
                if name:
                    names.setdefault(name, set()).add(label)
                if email and email.lower() != entity.value.lower():
                    emails.setdefault(email.lower(), set()).add(label)

        out: list[Entity] = []
        for name, servers in names.items():
            out.append(Entity.make(EntityType.NAME, name, source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id,
                                   metadata={"linked_via": "PGP key uid", "for_email": entity.value,
                                             "keyservers": sorted(servers)}))
        for email, servers in emails.items():
            out.append(Entity.make(EntityType.EMAIL, email, source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id,
                                   metadata={"linked_via": "shared PGP key", "with_email": entity.value,
                                             "keyservers": sorted(servers)}))
        if proton:
            out.append(Entity(type=EntityType.EMAIL, value=entity.value, source_module=self.name,
                              confidence=self.reliability, seed_id=entity.seed_id,
                              metadata={"proton_account": True,
                                        "note": "PGP key published on ProtonMail keyserver"}))
        return out


def _parse_uids(text: str) -> list[tuple[str, str]]:
    """Parse machine-readable (mr) keyserver output; return (name, email) from each uid line."""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("uid:"):
            continue
        uid = line.split(":", 2)[1] if line.count(":") >= 2 else ""
        # keyservers percent-encode some uid characters
        uid = uid.replace("%20", " ").strip()
        m = _UID.match(uid)
        if not m:
            continue
        outside, inside = m.group("outside").strip(), m.group("inside").strip()
        # Standard uid is "Name <email>", but some keys carry a malformed "email <Name>";
        # classify by which part is the address rather than trusting position.
        if _looks_email(inside) and not _looks_email(outside):
            name, email = outside, inside
        elif _looks_email(outside) and not _looks_email(inside):
            name, email = inside, outside
        else:
            name, email = outside, inside
        # Never let an address masquerade as a name, or vice versa.
        name = "" if _looks_email(name) else name
        email = email if _looks_email(email) else ""
        out.append((name, email))
    return out
