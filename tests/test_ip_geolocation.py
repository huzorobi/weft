"""IP geolocation (ip-api.com, mocked) and KML export."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.module import RunContext
from weft.modules.ip.ip_geolocation import IpGeolocation
from weft.reporting.kml import build_kml, has_geolocated_ips

from _fakes import FakeHttp

_GEO = {"status": "success", "country": "United States", "countryCode": "US",
        "regionName": "Virginia", "city": "Ashburn", "lat": 39.03, "lon": -77.5,
        "isp": "Google LLC", "org": "Google Public DNS", "as": "AS15169 Google LLC", "query": "8.8.8.8"}


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _ip(v="8.8.8.8"):
    return Entity.make(EntityType.IP, v, source_module="dns", confidence=0.9, seed_id="s")


def test_ip_geolocation_enriches_and_emits_org():
    out = asyncio.run(IpGeolocation().run(_ip(), _ctx(FakeHttp({"ip-api.com": (200, _GEO)}))))
    ip = [e for e in out if e.type is EntityType.IP][0]
    assert ip.key() == "ip:8.8.8.8"           # same node, enriched
    assert ip.metadata["lat"] == 39.03 and ip.metadata["lon"] == -77.5
    assert ip.metadata["city"] == "Ashburn"
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    assert orgs and orgs[0].value == "Google Public DNS"


def test_ip_geolocation_failure_returns_empty():
    out = asyncio.run(IpGeolocation().run(_ip(), _ctx(FakeHttp({"ip-api.com": (200, {"status": "fail"})}))))
    assert out == []


def test_kml_placemark_from_geolocated_ip():
    g = InMemoryGraph()
    g.upsert_entity(Entity(type=EntityType.IP, value="8.8.8.8", source_module="ip_geolocation",
                           confidence=0.7, seed_id="s",
                           metadata={"lat": 39.03, "lon": -77.5, "city": "Ashburn", "country": "United States"}))
    assert has_geolocated_ips(g)
    kml = build_kml(g)
    assert "<coordinates>-77.5,39.03,0</coordinates>" in kml     # lon,lat order
    assert "<name>8.8.8.8</name>" in kml
    assert "Ashburn" in kml
    assert kml.strip().startswith("<?xml")


def test_kml_empty_when_no_coordinates():
    g = InMemoryGraph()
    g.upsert_entity(Entity.make(EntityType.IP, "10.0.0.1", source_module="dns", confidence=0.9, seed_id="s"))
    assert not has_geolocated_ips(g)
    assert "<Placemark>" not in build_kml(g)


def test_registry_discovers_ip_geolocation():
    from weft.core import registry
    registry.discover()
    assert "ip_geolocation" in registry.registered_classes()
