"""ENS name <-> Ethereum address resolution (free, keyless, passive).

The Ethereum Name Service links a human name (vitalik.eth) to an address and back. This
module resolves in both directions via a public keyless resolver:
  - an ETH address (CRYPTO_ADDRESS 0x…) -> its primary ENS name, a strong identity pivot;
  - an ENS name (a USERNAME or DOMAIN ending .eth) -> its ETH address.
Passive read of a public resolver. Keyless.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

from ._chain import is_eth

RESOLVE = "https://api.ensideas.com/ens/resolve/"


@register
class EnsResolve(Module):
    name = "ens_resolve"
    accepts = [EntityType.CRYPTO_ADDRESS, EntityType.USERNAME, EntityType.DOMAIN]
    produces = [EntityType.CRYPTO_ADDRESS, EntityType.USERNAME, EntityType.URL]
    access = Access.FREE_API
    reliability = 0.85
    timeout_s = 20

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        query = _query_for(entity)
        if query is None:
            return []   # not an ETH address and not a .eth name — nothing to resolve
        status, data = await ctx.http.get_json(f"{RESOLVE}{query}")
        if status != 200 or not isinstance(data, dict):
            return []
        return _parse(data, entity, self.name, self.reliability)


def _query_for(entity: Entity) -> str | None:
    v = (entity.value or "").strip()
    if entity.type is EntityType.CRYPTO_ADDRESS:
        return v if is_eth(v) else None
    # USERNAME / DOMAIN: only resolve if it is an ENS name
    return v if v.lower().endswith(".eth") else None


def _parse(data: dict, seed: Entity, source: str, reliability: float) -> list[Entity]:
    out: list[Entity] = []
    address = data.get("address")
    name = data.get("name")
    if address and address != "0x0000000000000000000000000000000000000000":
        if seed.type is not EntityType.CRYPTO_ADDRESS:   # name -> address
            out.append(Entity.make(EntityType.CRYPTO_ADDRESS, address, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"chain": "ethereum", "resolved_from_ens": name or seed.value},
                                   label="ethereum"))
    if name:
        if seed.type is EntityType.CRYPTO_ADDRESS:       # address -> name
            out.append(Entity.make(EntityType.USERNAME, name, source_module=source,
                                   confidence=reliability, seed_id=seed.seed_id,
                                   metadata={"kind": "ens_name", "for_address": seed.value}))
        out.append(Entity.make(EntityType.URL, f"https://app.ens.domains/{name}", source_module=source,
                               confidence=reliability, seed_id=seed.seed_id, metadata={"role": "ens_profile"}))
    avatar = data.get("avatar")
    if avatar and str(avatar).startswith("http"):
        out.append(Entity.make(EntityType.URL, str(avatar), source_module=source,
                               confidence=reliability * 0.8, seed_id=seed.seed_id,
                               metadata={"role": "ens_avatar"}))
    return out
