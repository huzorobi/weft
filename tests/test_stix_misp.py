"""STIX 2.1 bundle + MISP event export."""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.reporting.stix import to_misp_event, to_stix_bundle


def _g():
    g = InMemoryGraph()
    em = Entity.make(EntityType.EMAIL, "rob@x.com", source_module="m", confidence=0.9, seed_id="s")
    dom = Entity.make(EntityType.DOMAIN, "x.com", source_module="m", confidence=0.8, seed_id="s")
    g.upsert_entity(em); g.upsert_entity(dom)
    g.upsert_entity(Entity.make(EntityType.IP, "1.2.3.4", source_module="m", confidence=0.7, seed_id="s"))
    g.upsert_entity(Entity.make(EntityType.PERSON, "Rob Huzo", source_module="m", confidence=0.8, seed_id="s"))
    g.upsert_entity(Entity.make(EntityType.CVE, "CVE-2021-44228", source_module="m", confidence=0.9, seed_id="s"))
    g.link(em, dom, via="whois", confidence=0.8)
    return g


def test_stix_bundle_shapes_objects_and_relationships():
    b = to_stix_bundle(_g())
    assert b["type"] == "bundle"
    types = {o["type"] for o in b["objects"]}
    assert {"email-addr", "domain-name", "ipv4-addr", "identity", "vulnerability", "relationship"} <= types
    email = next(o for o in b["objects"] if o["type"] == "email-addr")
    assert email["value"] == "rob@x.com" and email["spec_version"] == "2.1"
    ident = next(o for o in b["objects"] if o["type"] == "identity")
    assert ident["identity_class"] == "individual"
    rel = next(o for o in b["objects"] if o["type"] == "relationship")
    assert rel["source_ref"].startswith("email-addr--") and rel["target_ref"].startswith("domain-name--")


def test_stix_ids_are_deterministic():
    b1 = to_stix_bundle(_g())
    b2 = to_stix_bundle(_g())
    ids1 = sorted(o["id"] for o in b1["objects"] if o["type"] != "relationship")
    ids2 = sorted(o["id"] for o in b2["objects"] if o["type"] != "relationship")
    assert ids1 == ids2   # same graph -> same object ids (bundle id may differ)


def test_misp_event_typed_attributes():
    ev = to_misp_event(_g())["Event"]
    by_val = {a["value"]: a for a in ev["Attribute"]}
    assert by_val["1.2.3.4"]["type"] == "ip-dst" and by_val["1.2.3.4"]["to_ids"] is True
    assert by_val["rob@x.com"]["type"] == "email-src"
    assert by_val["CVE-2021-44228"]["type"] == "vulnerability"
    assert by_val["Rob Huzo"]["type"] == "target-user"


def test_misp_dedupes_attributes():
    g = InMemoryGraph()
    for _ in range(2):
        g.upsert_entity(Entity.make(EntityType.DOMAIN, "x.com", source_module="m", confidence=0.8, seed_id="s"))
    ev = to_misp_event(g)["Event"]
    assert len([a for a in ev["Attribute"] if a["value"] == "x.com"]) == 1
