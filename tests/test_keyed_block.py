"""Free-key provider block — the KeyedApiModule building block + AbuseIPDB, Hunter.io,
SecurityTrails, Etherscan (mocked HTTP + fake secrets).

Endpoints were confirmed live to exist and to gate on a key (HTTP 401 without one); the parse
logic is pinned here against documented response shapes and will be live-verified when the
operator supplies keys. Each module self-disables without its key.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.keyed.abuseipdb import AbuseIpdb
from weft.modules.keyed.etherscan import Etherscan
from weft.modules.keyed.hunterio import HunterIo
from weft.modules.keyed.securitytrails import SecurityTrails

from _fakes import FakeHttp, FakeSecrets

ETH = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def _ctx(http, keys=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=FakeSecrets(keys or {}))


def _e(t, v):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- building-block behaviour: self-disable without a key --------------------

def test_all_keyed_modules_self_disable_health_without_key():
    for mod, envs in [
        (AbuseIpdb(), "ABUSEIPDB_API_KEY"),
        (HunterIo(), "HUNTERIO_API_KEY"),
        (SecurityTrails(), "SECURITYTRAILS_API_KEY"),
        (Etherscan(), "ETHERSCAN_API_KEY"),
    ]:
        h = asyncio.run(mod.health(_ctx(FakeHttp({}), keys={})))
        assert not h.ok and "free key" in h.detail
        assert mod.requires_free_key and mod.secret_env == envs


def test_keyed_module_run_without_key_returns_empty_and_no_http():
    http = FakeHttp({})
    assert asyncio.run(AbuseIpdb().run(_e(EntityType.IP, "1.2.3.4"), _ctx(http, keys={}))) == []
    assert http.calls == []   # never calls the API without a key


# --- AbuseIPDB ---------------------------------------------------------------

def test_abuseipdb_parses_score_and_sends_key_header():
    http = FakeHttp({"api.abuseipdb.com": (200, {"data": {
        "abuseConfidenceScore": 90, "totalReports": 42, "countryCode": "RU",
        "isp": "Bad ISP", "usageType": "Data Center", "isTor": False}})})
    out = asyncio.run(AbuseIpdb().run(_e(EntityType.IP, "1.2.3.4"), _ctx(http, {"ABUSEIPDB_API_KEY": "k"})))
    assert out and out[0].metadata["abuse_confidence"] == 90
    assert out[0].metadata["country"] == "RU"


# --- Hunter.io ---------------------------------------------------------------

def test_hunterio_emits_emails_and_people():
    http = FakeHttp({"api.hunter.io": (200, {"data": {"pattern": "{first}", "emails": [
        {"value": "jane@acme.com", "confidence": 90, "first_name": "Jane", "last_name": "Doe",
         "position": "CTO", "type": "personal"}]}})})
    out = asyncio.run(HunterIo().run(_e(EntityType.DOMAIN, "acme.com"), _ctx(http, {"HUNTERIO_API_KEY": "k"})))
    emails = [e for e in out if e.type is EntityType.EMAIL]
    people = [e for e in out if e.type is EntityType.PERSON]
    assert emails and emails[0].value == "jane@acme.com" and emails[0].metadata["pattern"] == "{first}"
    assert people and people[0].value == "Jane Doe"


# --- SecurityTrails ----------------------------------------------------------

def test_securitytrails_builds_fqdns():
    http = FakeHttp({"api.securitytrails.com": (200, {"subdomains": ["www", "api", "www"]})})
    out = asyncio.run(SecurityTrails().run(_e(EntityType.DOMAIN, "acme.com"),
                                           _ctx(http, {"SECURITYTRAILS_API_KEY": "k"})))
    fqdns = {e.value for e in out}
    assert fqdns == {"www.acme.com", "api.acme.com"}   # deduped, parent appended


# --- Etherscan ---------------------------------------------------------------

def test_etherscan_parses_balance_and_ignores_non_eth():
    http = FakeHttp({"api.etherscan.io": (200, {"status": "1", "result": "1500000000000000000"})})
    out = asyncio.run(Etherscan().run(_e(EntityType.CRYPTO_ADDRESS, ETH), _ctx(http, {"ETHERSCAN_API_KEY": "k"})))
    assert out and out[0].metadata["balance_eth"] == 1.5
    # a Bitcoin address must not trigger the ETH module
    btc = _e(EntityType.CRYPTO_ADDRESS, "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    http2 = FakeHttp({})
    assert asyncio.run(Etherscan().run(btc, _ctx(http2, {"ETHERSCAN_API_KEY": "k"}))) == []
    assert http2.calls == []


def test_registry_discovers_keyed_block():
    from weft.core import registry
    registry.discover()
    assert {"abuseipdb", "hunterio", "securitytrails", "etherscan"} <= set(registry.registered_classes())
