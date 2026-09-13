"""Domain modules (crt.sh, Cert Spotter, RDAP) against mocked HTTP — no live calls."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.certspotter import CertSpotter
from weft.modules.domain.crtsh import CrtSh
from weft.modules.domain.rdap_whois import RdapWhois

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _seed():
    return Entity.make(EntityType.DOMAIN, "example.com", source_module="seed", confidence=1.0, seed_id="s1")


def test_crtsh_extracts_subdomains_strips_wildcards_and_apex():
    http = FakeHttp({"crt.sh": (200, [
        {"name_value": "*.example.com\nexample.com\napi.example.com"},
        {"name_value": "mail.example.com"},
        {"name_value": "other.net"},  # not under seed -> excluded
    ])})
    out = asyncio.run(CrtSh().run(_seed(), _ctx(http)))
    vals = {e.value for e in out}
    assert vals == {"api.example.com", "mail.example.com"}
    assert all(e.type is EntityType.DOMAIN for e in out)


def test_crtsh_non_json_returns_empty():
    out = asyncio.run(CrtSh().run(_seed(), _ctx(FakeHttp({"crt.sh": (200, None)}))))
    assert out == []


def test_certspotter_flattens_dns_names():
    http = FakeHttp({"certspotter": (200, [
        {"dns_names": ["example.com", "api.example.com", "*.dev.example.com"]},
        {"dns_names": ["vpn.example.com"]},
    ])})
    out = asyncio.run(CertSpotter().run(_seed(), _ctx(http)))
    vals = {e.value for e in out}
    assert vals == {"api.example.com", "dev.example.com", "vpn.example.com"}


def test_rdap_extracts_org_nameservers_and_dates():
    http = FakeHttp({"rdap.org/domain/example.com": (200, {
        "events": [
            {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2027-08-13T04:00:00Z"},
        ],
        "status": ["client delete prohibited"],
        "nameservers": [{"ldhName": "a.iana-servers.net"}, {"ldhName": "b.iana-servers.net"}],
        "entities": [{
            "roles": ["registrant"],
            "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["org", {}, "text", "Acme Corp"]]],
        }],
    })})
    out = asyncio.run(RdapWhois().run(_seed(), _ctx(http)))
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    ns = [e for e in out if e.type is EntityType.DOMAIN and e.metadata.get("record") == "ns"]
    domain_node = [e for e in out if e.type is EntityType.DOMAIN and "registration_events" in e.metadata]
    assert orgs and orgs[0].value == "Acme Corp"
    assert {e.value for e in ns} == {"a.iana-servers.net", "b.iana-servers.net"}
    assert domain_node and domain_node[0].metadata["registration_events"]["registration"].startswith("1995")


def test_rdap_redacted_registrant_is_not_invented():
    http = FakeHttp({"rdap.org/domain/example.com": (200, {
        "events": [], "status": [], "nameservers": [], "entities": [],
    })})
    out = asyncio.run(RdapWhois().run(_seed(), _ctx(http)))
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    assert orgs == []
    node = [e for e in out if e.type is EntityType.DOMAIN][0]
    assert node.metadata["registrant"] == "redacted or not public"
