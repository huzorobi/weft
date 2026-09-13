"""Bitcoin address activity via mempool.space (free, keyless, passive).

Reads a public block explorer's already-indexed view of a BTC address: total received/sent,
current balance, and transaction count. Passive — Weft reads the explorer's index, it does
not touch any wallet or node. Keyless. Falls back to blockchain.info if mempool.space is down.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

from ._chain import is_btc

MEMPOOL = "https://mempool.space/api/address/"
BLOCKCHAIN_INFO = "https://blockchain.info/rawaddr/"
SATS = 100_000_000  # satoshis per BTC


@register
class BlockchainBtc(Module):
    name = "blockchain_btc"
    accepts = [EntityType.CRYPTO_ADDRESS]
    produces = [EntityType.CRYPTO_ADDRESS]
    access = Access.FREE_API
    reliability = 0.9   # authoritative on-chain data
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None or not is_btc(entity.value):
            return []   # not a Bitcoin address — leave it for another chain's module
        stats = await self._mempool(entity.value, ctx) or await self._blockchain_info(entity.value, ctx)
        if stats is None:
            return []
        return _emit(entity, stats, self.name, self.reliability)

    async def _mempool(self, addr: str, ctx) -> dict | None:
        status, data = await ctx.http.get_json(f"{MEMPOOL}{addr}")
        if status != 200 or not isinstance(data, dict) or "chain_stats" not in data:
            return None
        c = data.get("chain_stats", {}) or {}
        recv = int(c.get("funded_txo_sum", 0))
        sent = int(c.get("spent_txo_sum", 0))
        return {
            "total_received_btc": recv / SATS,
            "total_sent_btc": sent / SATS,
            "balance_btc": (recv - sent) / SATS,
            "tx_count": int(c.get("tx_count", 0)),
            "explorer": "mempool.space",
        }

    async def _blockchain_info(self, addr: str, ctx) -> dict | None:
        status, data = await ctx.http.get_json(f"{BLOCKCHAIN_INFO}{addr}", params={"limit": 0})
        if status != 200 or not isinstance(data, dict) or "final_balance" not in data:
            return None
        return {
            "total_received_btc": int(data.get("total_received", 0)) / SATS,
            "total_sent_btc": int(data.get("total_sent", 0)) / SATS,
            "balance_btc": int(data.get("final_balance", 0)) / SATS,
            "tx_count": int(data.get("n_tx", 0)),
            "explorer": "blockchain.info",
        }


def _emit(entity: Entity, stats: dict, source: str, reliability: float) -> list[Entity]:
    # The explorer link goes in metadata, not as a URL entity: URL normalisation lower-cases,
    # and a Bitcoin base58 address is case-sensitive, so a URL node would be a dead link.
    enriched = Entity(
        type=EntityType.CRYPTO_ADDRESS, value=entity.value, source_module=source,
        confidence=reliability, seed_id=entity.seed_id,
        metadata={"chain": "bitcoin", "explorer_url": f"https://mempool.space/address/{entity.value}", **stats},
        label="bitcoin",
    )
    return [enriched]
