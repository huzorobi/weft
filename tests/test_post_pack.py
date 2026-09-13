"""POST-capable pack — npm PACKAGE emission, OSV package vulns, abuse.ch (mocked HTTP).

Exercises the new post_json client path via the fake. OSV was live-verified over POST; abuse.ch
endpoints were confirmed to gate on a key (HTTP 401), parse pinned here.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.keyed.abusech import AbuseCh
from weft.modules.username.npm import Npm
from weft.modules.vuln.osv_package import OsvPackage

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, keys=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=FakeSecrets(keys or {}))


def _e(t, v):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- npm now emits PACKAGE entities ------------------------------------------

def test_npm_emits_package_entity():
    http = FakeHttp({"registry.npmjs.org/-/v1/search": (200, {"objects": [
        {"package": {"name": "lodash", "publisher": {"username": "jdalton"},
                     "links": {"npm": "https://www.npmjs.com/package/lodash"}}}]})})
    out = asyncio.run(Npm().run(_e(EntityType.USERNAME, "jdalton"), _ctx(http)))
    pkgs = [e for e in out if e.type is EntityType.PACKAGE]
    assert pkgs and pkgs[0].value == "npm:lodash"
    assert pkgs[0].metadata == {"ecosystem": "npm", "name": "lodash"}


# --- OSV package -> CVE chain ------------------------------------------------

def test_osv_package_emits_cves_and_advisory():
    http = FakeHttp({"api.osv.dev/v1/query": (200, {"vulns": [
        {"id": "GHSA-29mw-wpgm-hmr9", "summary": "Prototype pollution in lodash",
         "aliases": ["CVE-2020-8203", "GHSA-29mw-wpgm-hmr9"]}]})})
    out = asyncio.run(OsvPackage().run(_e(EntityType.PACKAGE, "npm:lodash"), _ctx(http)))
    cves = {e.value for e in out if e.type is EntityType.CVE}
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert "CVE-2020-8203" in cves
    # URL entities are lower-cased by normalisation; osv.dev's advisory page is case-insensitive,
    # and the correct-case id is kept in metadata.
    assert "https://osv.dev/vulnerability/ghsa-29mw-wpgm-hmr9" in urls
    advisory = next(e for e in out if e.type is EntityType.URL)
    assert advisory.metadata["advisory_id"] == "GHSA-29mw-wpgm-hmr9"


def test_osv_package_maps_ecosystem_case():
    # a PyPI package must be queried with the capitalised ecosystem OSV expects
    http = FakeHttp({"api.osv.dev/v1/query": (200, {"vulns": []})})
    asyncio.run(OsvPackage().run(_e(EntityType.PACKAGE, "pypi:django"), _ctx(http)))
    assert any("PyPI" in c for c in http.calls)   # the POST body carried the mapped ecosystem


def test_osv_package_no_ecosystem_prefix_returns_empty():
    assert asyncio.run(OsvPackage().run(_e(EntityType.PACKAGE, "lodash"), _ctx(FakeHttp({})))) == []


# --- abuse.ch (keyed, POST) --------------------------------------------------

def test_abusech_self_disables_without_key():
    http = FakeHttp({})
    out = asyncio.run(AbuseCh().run(_e(EntityType.IP, "1.2.3.4"), _ctx(http, keys={})))
    assert out == [] and http.calls == []


def test_abusech_parses_threatfox_and_urlhaus():
    http = FakeHttp({
        "threatfox-api.abuse.ch": (200, {"query_status": "ok", "data": [
            {"threat_type": "botnet_cc", "malware_printable": "Cobalt Strike", "confidence_level": 100,
             "first_seen": "2026-01-01"}]}),
        "urlhaus-api.abuse.ch": (200, {"query_status": "ok", "urls": [
            {"url": "http://evil.example/payload.exe", "url_status": "online", "threat": "malware_download",
             "date_added": "2026-02-02"}]}),
    })
    out = asyncio.run(AbuseCh().run(_e(EntityType.IP, "1.2.3.4"), _ctx(http, {"ABUSECH_API_KEY": "k"})))
    iocs = [e for e in out if e.type is EntityType.IP]
    urls = [e for e in out if e.type is EntityType.URL]
    assert iocs and iocs[0].metadata["malware"] == "Cobalt Strike"
    assert urls and urls[0].value == "http://evil.example/payload.exe"


def test_abusech_no_result_returns_empty():
    http = FakeHttp({"threatfox-api.abuse.ch": (200, {"query_status": "no_result"}),
                     "urlhaus-api.abuse.ch": (200, {"query_status": "no_results"})})
    assert asyncio.run(AbuseCh().run(_e(EntityType.DOMAIN, "clean.example"), _ctx(http, {"ABUSECH_API_KEY": "k"}))) == []


def test_registry_discovers_post_pack():
    from weft.core import registry
    registry.discover()
    assert {"osv_package", "abusech"} <= set(registry.registered_classes())
