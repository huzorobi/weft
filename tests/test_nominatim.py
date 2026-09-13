"""Nominatim address geocoding + address placemarks in the KML map."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.module import RunContext
from weft.modules.name.nominatim import Nominatim
from weft.reporting.kml import build_kml, has_geolocated_ips

from _fakes import FakeHttp


def test_nominatim_enriches_address_with_coords():
    http = FakeHttp({"nominatim.openstreetmap.org": (200, [
        {"lat": "51.5209589", "lon": "-0.0811407", "display_name": "Monzo Bank, 5 Appold Street, London"}])})
    ctx = RunContext(engagement_id="e", operator="r", allow_tos_risk=False, depth=0, http=http)
    addr = Entity.make(EntityType.ADDRESS, "5 Appold Street, London", source_module="gleif", confidence=0.7, seed_id="s")
    out = asyncio.run(Nominatim().run(addr, ctx))
    assert out and out[0].type is EntityType.ADDRESS
    assert out[0].metadata["lat"] == 51.5209589 and out[0].metadata["lon"] == -0.0811407
    assert out[0].key() == addr.key()   # enriched in place


def test_kml_includes_geocoded_address():
    g = InMemoryGraph()
    g.upsert_entity(Entity(type=EntityType.ADDRESS, value="5 Appold Street, London", source_module="nominatim",
                           confidence=0.6, seed_id="s",
                           metadata={"lat": 51.52, "lon": -0.08, "geocoded_name": "Monzo Bank"}))
    assert has_geolocated_ips(g)
    kml = build_kml(g)
    assert "<coordinates>-0.08,51.52,0</coordinates>" in kml
    assert "address" in kml


def test_registry_discovers_nominatim():
    from weft.core import registry
    registry.discover()
    assert "nominatim" in registry.registered_classes()
