"""Tiny, dependency-free classifier for a crypto address string.

Deterministic shape checks only — never a network call. Modules use these to fire on the
right chain and skip an address that is not theirs (so a BTC module ignores an ETH address).
"""
from __future__ import annotations

import re

_ETH = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Bitcoin has two families with different alphabets:
#   base58 P2PKH/P2SH — starts 1 or 3, excludes 0 O I l
_BTC_BASE58 = re.compile(r"^[13][1-9A-HJ-NP-Za-km-z]{25,39}$")
#   bech32/bech32m (SegWit) — starts bc1, lowercase bech32 alphabet
_BTC_BECH32 = re.compile(r"^bc1[023456789ac-hj-np-z]{6,87}$")


def is_eth(value: str) -> bool:
    return bool(_ETH.match((value or "").strip()))


def is_btc(value: str) -> bool:
    v = (value or "").strip()
    if is_eth(v):
        return False
    return bool(_BTC_BASE58.match(v) or _BTC_BECH32.match(v))
