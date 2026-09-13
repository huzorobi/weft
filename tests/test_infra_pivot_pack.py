"""Infrastructure-pivot pack — ARIN RDAP + HackerTarget reverse-IP/hostsearch (mocked HTTP).

Shapes here mirror the live responses verified against rdap.arin.net and api.hackertarget.com.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.hackertarget import HackerTarget
from weft.modules.ip.arin_rdap import ArinRdap

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _ip(v="8.8.8.8"):
    return Entity.make(EntityType.IP, v, source_module="seed", confidence=1.0, seed_id="s")


def _domain(v="github.com"):
    return Entity.make(EntityType.DOMAIN, v, source_module="seed", confidence=1.0, seed_id="s")


# --- ARIN RDAP ---------------------------------------------------------------

ARIN_RESPONSE = {
    "name": "GOGL", "handle": "NET-8-8-8-0-2", "type": "DIRECT ALLOCATION",
    "cidr0_cidrs": [{"v4prefix": "8.8.8.0", "length": 24}],
    "entities": [{
        "handle": "GOGL", "roles": ["registrant"],
        "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Google LLC"]]],
        "entities": [{
            "handle": "ABUSE5250-ARIN", "roles": ["abuse"],
            "vcardArray": ["vcard", [["fn", {}, "text", "Abuse"], ["email", {}, "text", "network-abuse@google.com"]]],
        }],
    }],
}


def test_arin_parses_org_cidr_and_abuse_email():
    out = asyncio.run(ArinRdap().run(_ip(), _ctx(FakeHttp({"rdap.arin.net": (200, ARIN_RESPONSE)}))))
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    emails = [e for e in out if e.type is EntityType.EMAIL]
    assert orgs and orgs[0].value == "Google LLC"
    assert orgs[0].metadata["cidr"] == "8.8.8.0/24"
    assert orgs[0].metadata["network_name"] == "GOGL"
    assert orgs[0].metadata["registry"] == "ARIN"
    assert emails and emails[0].value == "network-abuse@google.com"
    assert "abuse" in emails[0].metadata["role"]


def test_arin_non_arin_space_returns_empty():
    # ARIN returns 404 (or a redirect handled upstream) for non-NA space
    out = asyncio.run(ArinRdap().run(_ip("193.0.6.139"), _ctx(FakeHttp({"rdap.arin.net": (404, None)}))))
    assert out == []


# --- HackerTarget reverse IP -------------------------------------------------

def test_hackertarget_reverse_ip_yields_cohosted_domains():
    body = "example.com\nfoo.example.net\n5.5.5.5.in-addr.arpa\n\nbar.org\n"
    http = FakeHttp({"reverseiplookup": (200, body)})
    out = asyncio.run(HackerTarget().run(_ip(), _ctx(http)))
    domains = {e.value for e in out if e.type is EntityType.DOMAIN}
    assert domains == {"example.com", "foo.example.net", "bar.org"}   # .arpa + blank dropped
    assert all(e.metadata["on_ip"] == "8.8.8.8" for e in out)


def test_hackertarget_hostsearch_yields_subdomains_and_ips():
    body = "github.com,140.82.113.3\napi.github.com,140.82.113.5\n"
    http = FakeHttp({"hostsearch": (200, body)})
    out = asyncio.run(HackerTarget().run(_domain(), _ctx(http)))
    domains = {e.value for e in out if e.type is EntityType.DOMAIN}
    ips = {e.value for e in out if e.type is EntityType.IP}
    assert "api.github.com" in domains
    assert "140.82.113.3" in ips and "140.82.113.5" in ips


def test_hackertarget_rate_limit_body_returns_empty():
    http = FakeHttp({"reverseiplookup": (200, "API count exceeded - Your free membership limit...")})
    assert asyncio.run(HackerTarget().run(_ip(), _ctx(http))) == []


def test_hackertarget_routes_by_entity_type():
    # a DOMAIN seed must hit hostsearch, not reverseiplookup
    http = FakeHttp({"hostsearch": (200, "x.github.com,1.2.3.4\n"), "reverseiplookup": (200, "SHOULD-NOT-BE-USED\n")})
    asyncio.run(HackerTarget().run(_domain(), _ctx(http)))
    assert any("hostsearch" in c for c in http.calls)
    assert not any("reverseiplookup" in c for c in http.calls)


def test_registry_discovers_infra_pivot_pack():
    from weft.core import registry
    registry.discover()
    assert {"arin_rdap", "hackertarget"} <= set(registry.registered_classes())
