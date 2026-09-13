"""Crypto-address pack — BTC explorer + ENS resolution (mocked HTTP).

Live-verified against mempool.space, blockchain.info, and api.ensideas.com before shipping;
these tests pin the parse logic and the chain-guard behaviour offline.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType, normalise_value
from weft.core.module import RunContext
from weft.modules.crypto._chain import is_btc, is_eth
from weft.modules.crypto.blockchain_btc import BlockchainBtc
from weft.modules.crypto.ens_resolve import EnsResolve

from _fakes import FakeHttp

BTC = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
ETH = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _addr(v, t=EntityType.CRYPTO_ADDRESS):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- chain classifier + normalisation ---------------------------------------

def test_chain_classifier_separates_btc_and_eth():
    assert is_btc(BTC) and not is_eth(BTC)
    assert is_eth(ETH) and not is_btc(ETH)
    assert is_btc("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")
    assert not is_btc("notanaddress") and not is_eth("0xzz")


def test_eth_address_normalised_lowercase_btc_preserved():
    assert normalise_value(EntityType.CRYPTO_ADDRESS, ETH) == ETH.lower()
    assert normalise_value(EntityType.CRYPTO_ADDRESS, BTC) == BTC  # case preserved


# --- Bitcoin explorer --------------------------------------------------------

def test_btc_mempool_parses_balance_and_url():
    http = FakeHttp({f"mempool.space/api/address/{BTC}": (200, {
        "address": BTC,
        "chain_stats": {"funded_txo_sum": 10_00000000, "spent_txo_sum": 3_00000000, "tx_count": 42},
    })})
    out = asyncio.run(BlockchainBtc().run(_addr(BTC), _ctx(http)))
    coins = [e for e in out if e.type is EntityType.CRYPTO_ADDRESS]
    assert coins and coins[0].metadata["chain"] == "bitcoin"
    assert coins[0].metadata["balance_btc"] == 7.0
    assert coins[0].metadata["total_received_btc"] == 10.0
    assert coins[0].metadata["tx_count"] == 42
    assert coins[0].metadata["explorer"] == "mempool.space"
    # explorer link is in metadata (URL nodes are lower-cased; BTC addresses are case-sensitive)
    assert coins[0].metadata["explorer_url"] == f"https://mempool.space/address/{BTC}"


def test_btc_falls_back_to_blockchain_info_when_mempool_down():
    http = FakeHttp({
        f"mempool.space/api/address/{BTC}": (503, None),
        f"blockchain.info/rawaddr/{BTC}": (200, {
            "final_balance": 5_00000000, "total_received": 8_00000000, "total_sent": 3_00000000, "n_tx": 9}),
    })
    out = asyncio.run(BlockchainBtc().run(_addr(BTC), _ctx(http)))
    coins = [e for e in out if e.type is EntityType.CRYPTO_ADDRESS]
    assert coins and coins[0].metadata["explorer"] == "blockchain.info"
    assert coins[0].metadata["balance_btc"] == 5.0


def test_btc_module_ignores_eth_address():
    # given an ETH address the BTC module must not fire (and must not call HTTP)
    http = FakeHttp({})
    out = asyncio.run(BlockchainBtc().run(_addr(ETH), _ctx(http)))
    assert out == []
    assert http.calls == []


# --- ENS ---------------------------------------------------------------------

def test_ens_reverse_address_to_name():
    http = FakeHttp({f"ensideas.com/ens/resolve/{ETH.lower()}": (200, {
        "address": ETH, "name": "vitalik.eth", "avatar": "https://metadata.ens.domains/x.png"})})
    out = asyncio.run(EnsResolve().run(_addr(ETH), _ctx(http)))
    names = [e for e in out if e.type is EntityType.USERNAME]
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert names and names[0].value == "vitalik.eth"
    assert names[0].metadata["kind"] == "ens_name"
    assert "https://app.ens.domains/vitalik.eth" in urls


def test_ens_forward_name_to_address():
    http = FakeHttp({"ensideas.com/ens/resolve/vitalik.eth": (200, {
        "address": ETH, "name": "vitalik.eth"})})
    seed = _addr("vitalik.eth", EntityType.USERNAME)
    out = asyncio.run(EnsResolve().run(seed, _ctx(http)))
    coins = [e for e in out if e.type is EntityType.CRYPTO_ADDRESS]
    assert coins and coins[0].value == ETH.lower()
    assert coins[0].metadata["chain"] == "ethereum"


def test_ens_skips_non_eth_address_and_non_eth_name():
    http = FakeHttp({})
    assert asyncio.run(EnsResolve().run(_addr(BTC), _ctx(http))) == []          # BTC addr, not ETH
    assert asyncio.run(EnsResolve().run(_addr("bob", EntityType.USERNAME), _ctx(http))) == []  # not .eth
    assert http.calls == []


# --- discovery ---------------------------------------------------------------

def test_registry_discovers_crypto_modules():
    from weft.core import registry
    registry.discover()
    assert {"blockchain_btc", "ens_resolve"} <= set(registry.registered_classes())
