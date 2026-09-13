"""Ethereum address activity via Etherscan (free key, passive).

For an Ethereum address, Etherscan returns the on-chain balance and transaction count — the
EVM counterpart to the keyless Bitcoin explorer. Uses Etherscan's V2 multichain endpoint
(chainid 1 = Ethereum mainnet). Free tier allows a generous request rate. Self-disables
without a key. Only fires on Ethereum-shaped addresses.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.keyed import KeyedApiModule
from weft.core.registry import register
from weft.modules.crypto._chain import is_eth

API = "https://api.etherscan.io/v2/api"
WEI = 10 ** 18


@register
class Etherscan(KeyedApiModule):
    name = "etherscan"
    accepts = [EntityType.CRYPTO_ADDRESS]
    produces = [EntityType.CRYPTO_ADDRESS]
    secret_env = "ETHERSCAN_API_KEY"
    reliability = 0.9
    timeout_s = 25

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        key = self._key(ctx)
        if ctx.http is None or not key or not is_eth(entity.value):
            return []
        base = {"chainid": "1", "address": entity.value, "apikey": key}
        status, bal = await ctx.http.get_json(
            API, params={**base, "module": "account", "action": "balance", "tag": "latest"})
        if status != 200 or not isinstance(bal, dict) or str(bal.get("status")) != "1":
            return []
        meta = {"chain": "ethereum", "balance_eth": int(bal.get("result", 0)) / WEI}
        status, txs = await ctx.http.get_json(
            API, params={**base, "module": "account", "action": "txlist", "page": "1",
                         "offset": "1", "sort": "asc"})
        if status == 200 and isinstance(txs, dict) and isinstance(txs.get("result"), list) and txs["result"]:
            first = txs["result"][0]
            meta["first_tx_time"] = first.get("timeStamp")
            meta["first_tx_from"] = first.get("from")
        return [Entity(type=EntityType.CRYPTO_ADDRESS, value=entity.value, source_module=self.name,
                       confidence=self.reliability, seed_id=entity.seed_id, metadata=meta,
                       label="ethereum")]
