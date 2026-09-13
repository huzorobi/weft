"""Keyless, verified OSINT sources — RIPEstat, Shodan InternetDB, Keybase, SEC EDGAR.

All four are free and require no API key. Each was live-verified against the real service
before shipping; these tests pin the parse logic against canned payloads so a schema drift
or a regression is caught offline.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.ip.ripestat import RipeStat
from weft.modules.ip.shodan_internetdb import ShodanInternetDB
from weft.modules.name.sec_edgar import SecEdgar
from weft.modules.username.keybase import Keybase

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _ip(v="8.8.8.8"):
    return Entity.make(EntityType.IP, v, source_module="seed", confidence=1.0, seed_id="s")


def _username(v="gakonst"):
    return Entity.make(EntityType.USERNAME, v, source_module="seed", confidence=1.0, seed_id="s")


def _name(v="Palantir Technologies"):
    return Entity.make(EntityType.NAME, v, source_module="seed", confidence=1.0, seed_id="s")


# --- Shodan InternetDB -------------------------------------------------------

def test_internetdb_enriches_ip_and_emits_hostnames():
    http = FakeHttp({"internetdb.shodan.io/8.8.8.8": (200, {
        "ip": "8.8.8.8", "ports": [53, 443], "cpes": ["cpe:/a:x"],
        "vulns": ["CVE-2021-1"], "tags": ["cdn"], "hostnames": ["dns.google", "DNS.GOOGLE."],
    })})
    out = asyncio.run(ShodanInternetDB().run(_ip(), _ctx(http)))
    ips = [e for e in out if e.type is EntityType.IP]
    domains = {e.value for e in out if e.type is EntityType.DOMAIN}
    assert ips and ips[0].metadata["ports"] == [53, 443]
    assert ips[0].metadata["vulns"] == ["CVE-2021-1"]
    assert domains == {"dns.google"}  # deduped + normalised (trailing dot / case stripped)


def test_internetdb_404_no_record_returns_empty():
    out = asyncio.run(ShodanInternetDB().run(_ip("10.0.0.1"), _ctx(FakeHttp({}))))
    assert out == []


# --- RIPEstat ----------------------------------------------------------------

def test_ripestat_abuse_contact_and_asn():
    http = FakeHttp({
        "abuse-contact-finder": (200, {"data": {"abuse_contacts": ["network-abuse@google.com"]}}),
        "network-info": (200, {"data": {"asns": ["15169"], "prefix": "8.8.8.0/24"}}),
    })
    out = asyncio.run(RipeStat().run(_ip(), _ctx(http)))
    emails = {e.value for e in out if e.type is EntityType.EMAIL}
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    assert "network-abuse@google.com" in emails
    assert orgs and orgs[0].value == "AS15169" and orgs[0].metadata["prefix"] == "8.8.8.0/24"


def test_ripestat_empty_data_returns_nothing():
    http = FakeHttp({
        "abuse-contact-finder": (200, {"data": {"abuse_contacts": []}}),
        "network-info": (200, {"data": {"asns": []}}),
    })
    assert asyncio.run(RipeStat().run(_ip(), _ctx(http))) == []


# --- Keybase -----------------------------------------------------------------

def test_keybase_emits_verified_proofs_and_profile():
    http = FakeHttp({"user/lookup.json": (200, {"them": [{
        "basics": {"username": "gakonst"},
        "proofs_summary": {"all": [
            {"proof_type": "twitter", "nametag": "gakonst",
             "service_url": "https://twitter.com/gakonst", "proof_url": "https://x/p1"},
            {"proof_type": "github", "nametag": "gakonst",
             "service_url": "https://github.com/gakonst", "proof_url": "https://x/p2"},
        ]},
    }]})})
    out = asyncio.run(Keybase().run(_username(), _ctx(http)))
    socials = {e.value for e in out if e.type is EntityType.SOCIAL_PROFILE}
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert "https://twitter.com/gakonst" in socials
    assert "https://github.com/gakonst" in socials
    assert "https://keybase.io/gakonst" in urls
    assert all(e.metadata.get("verified") for e in out if e.type is EntityType.SOCIAL_PROFILE)


def test_keybase_unknown_user_returns_empty():
    out = asyncio.run(Keybase().run(_username("nobody"), _ctx(FakeHttp({"user/lookup.json": (200, {"them": []})}))))
    assert out == []


# --- SEC EDGAR ---------------------------------------------------------------

def test_sec_edgar_parses_company_and_cik():
    http = FakeHttp({"efts.sec.gov": (200, {"hits": {"hits": [
        {"_source": {"display_names": ["Palantir Technologies Inc.  (PLTR) (CIK 0001321655)"]}},
        {"_source": {"display_names": ["Palantir Technologies Inc.  (PLTR) (CIK 0001321655)"]}},  # dupe
    ]}})})
    out = asyncio.run(SecEdgar().run(_name(), _ctx(http)))
    assert len(out) == 1  # deduped
    org = out[0]
    assert org.type is EntityType.ORGANISATION
    assert org.value.startswith("Palantir Technologies")
    assert org.metadata["cik"] == "0001321655"
    assert org.metadata["registry"] == "SEC EDGAR (US)"


def test_sec_edgar_no_hits_returns_empty():
    out = asyncio.run(SecEdgar().run(_name("zzzznotacompany"), _ctx(FakeHttp({"efts.sec.gov": (200, {"hits": {"hits": []}})}))))
    assert out == []


# --- discovery ---------------------------------------------------------------

def test_registry_discovers_all_four():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {"ripestat", "shodan_internetdb", "keybase", "sec_edgar"} <= names
