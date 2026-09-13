"""PGP keyservers (identity) + CVE context (CISA KEV + OSV) — mocked HTTP.

Shapes mirror the live keyserver MR output and the KEV/OSV JSON verified before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.email.pgp_keyservers import PgpKeyservers, _parse_uids
from weft.modules.ip.shodan_internetdb import ShodanInternetDB
from weft.modules.vuln.cve_context import CveContext

from _fakes import FakeHttp

UBUNTU_MR = (
    "info:1:2\n"
    "pub:6AFDDB6B447170715E61ADE5E40F771F68294F39:19:1027:1711673453::\n"
    "uid:Linus Torvalds <torvalds@kernel.org>:1711673453::\n"
    "uid:Linus Torvalds <torvalds@linux-foundation.org>:1711673453::\n"
)
PROTON_MR = (
    "info:1:1\r\n"
    "pub:3de9e6aae558521d5292cdc398ceda31d49cfd48:1:4096:1522360476::\r\n"
    "uid:info@protonmail.com <info@protonmail.com>:1522360476::\r\n"
)


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _email(v="torvalds@kernel.org"):
    return Entity.make(EntityType.EMAIL, v, source_module="seed", confidence=1.0, seed_id="s")


def _cve(v="CVE-2021-44228"):
    return Entity.make(EntityType.CVE, v, source_module="seed", confidence=1.0, seed_id="s")


# --- PGP keyservers ----------------------------------------------------------

def test_parse_uids_extracts_name_and_email():
    uids = _parse_uids(UBUNTU_MR)
    assert ("Linus Torvalds", "torvalds@kernel.org") in uids
    assert ("Linus Torvalds", "torvalds@linux-foundation.org") in uids


def test_pgp_yields_name_and_alias_email():
    # ubuntu has the key with two uids; the second email is an alias of the seed
    http = FakeHttp({
        "keyserver.ubuntu.com": (200, UBUNTU_MR),
        "keys.openpgp.org": (404, "No key found"),
        "protonmail": (404, "No key found"),
    })
    out = asyncio.run(PgpKeyservers().run(_email(), _ctx(http)))
    names = {e.value for e in out if e.type is EntityType.NAME}
    emails = {e.value for e in out if e.type is EntityType.EMAIL}
    assert "Linus Torvalds" in names
    assert "torvalds@linux-foundation.org" in emails      # alias found via shared key
    assert "torvalds@kernel.org" not in emails            # seed itself not re-emitted as alias


def test_pgp_flags_proton_account():
    http = FakeHttp({
        "keyserver.ubuntu.com": (404, "x"), "keys.openpgp.org": (404, "x"),
        "protonmail": (200, PROTON_MR),
    })
    out = asyncio.run(PgpKeyservers().run(_email("info@protonmail.com"), _ctx(http)))
    assert any(e.metadata.get("proton_account") for e in out if e.type is EntityType.EMAIL)


def test_pgp_no_keys_returns_empty():
    http = FakeHttp({"keyserver.ubuntu.com": (404, "no"), "keys.openpgp.org": (404, "no"), "protonmail": (404, "no")})
    assert asyncio.run(PgpKeyservers().run(_email(), _ctx(http))) == []


# --- Shodan InternetDB now emits CVE entities --------------------------------

def test_shodan_internetdb_emits_cve_entities():
    http = FakeHttp({"internetdb.shodan.io/1.2.3.4": (200, {
        "ip": "1.2.3.4", "ports": [443], "vulns": ["CVE-2021-44228", "CVE-2019-0708"], "hostnames": []})})
    ip = Entity.make(EntityType.IP, "1.2.3.4", source_module="seed", confidence=1.0, seed_id="s")
    out = asyncio.run(ShodanInternetDB().run(ip, _ctx(http)))
    cves = {e.value for e in out if e.type is EntityType.CVE}
    assert cves == {"CVE-2021-44228", "CVE-2019-0708"}


# --- CVE context -------------------------------------------------------------

KEV = {"count": 1, "vulnerabilities": [{
    "cveID": "CVE-2021-44228", "vulnerabilityName": "Apache Log4j2 RCE",
    "dateAdded": "2021-12-10", "dueDate": "2021-12-24", "knownRansomwareCampaignUse": "Known"}]}
OSV = {"id": "CVE-2021-44228", "summary": "Log4Shell",
       "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/.../C:H"}],
       "aliases": ["GHSA-jfh8-c2jp-5v3q", "CVE-2021-44228"]}


def _cve_http(kev=KEV, osv=OSV):
    return FakeHttp({"known_exploited_vulnerabilities.json": (200, kev),
                     "api.osv.dev/v1/vulns/": (200, osv)})


def test_cve_context_flags_known_exploited_with_kev_and_osv():
    out = asyncio.run(CveContext().run(_cve(), _ctx(_cve_http())))
    assert out and out[0].type is EntityType.CVE
    md = out[0].metadata
    assert md["known_exploited"] is True
    assert md["kev_name"] == "Apache Log4j2 RCE"
    assert md["ransomware_use"] == "Known"
    assert md["osv_summary"] == "Log4Shell"
    assert "GHSA-jfh8-c2jp-5v3q" in md["aliases"]


def test_cve_context_not_in_kev_but_osv_still_enriches():
    out = asyncio.run(CveContext().run(_cve("CVE-2019-0708"), _ctx(_cve_http(kev={"vulnerabilities": []}))))
    assert out and out[0].metadata["known_exploited"] is False
    assert out[0].metadata["osv_summary"] == "Log4Shell"


def test_cve_context_unknown_cve_returns_empty():
    http = FakeHttp({"known_exploited_vulnerabilities.json": (200, {"vulnerabilities": []}),
                     "api.osv.dev/v1/vulns/": (404, None)})
    assert asyncio.run(CveContext().run(_cve("CVE-2000-0001"), _ctx(http))) == []


def test_cve_context_caches_kev_across_cves():
    http = _cve_http()
    mod = CveContext()
    asyncio.run(mod.run(_cve(), _ctx(http)))
    asyncio.run(mod.run(_cve(), _ctx(http)))
    assert sum(1 for c in http.calls if "known_exploited" in c) == 1


def test_registry_discovers_identity_vuln_pack():
    from weft.core import registry
    registry.discover()
    assert {"pgp_keyservers", "cve_context"} <= set(registry.registered_classes())
