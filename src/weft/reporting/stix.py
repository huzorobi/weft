"""Export the graph to STIX 2.1 and MISP for interop with OpenCTI / MISP.

Produces standards-shaped JSON without a heavy SDK dependency: a STIX 2.1 bundle of observable
objects (email addresses, domains, IPs, URLs), identities (people/organisations), and
vulnerabilities, linked by relationships from the graph edges; and a MISP event with typed
attributes. Object ids are deterministic (uuid5 of type+value) so re-exporting the same graph
yields stable ids. Pure and deterministic.
"""
from __future__ import annotations

import uuid

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph

_NS = uuid.UUID("6f1e0c9a-1b2c-4d3e-8f5a-9b0c1d2e3f40")   # fixed Weft namespace

# EntityType -> (STIX type, the field that holds the value)
_STIX_SCO = {
    EntityType.EMAIL: ("email-addr", "value"),
    EntityType.DOMAIN: ("domain-name", "value"),
    EntityType.IP: ("ipv4-addr", "value"),
    EntityType.URL: ("url", "value"),
    EntityType.SOCIAL_PROFILE: ("url", "value"),
}
_STIX_IDENTITY = {EntityType.PERSON: "individual", EntityType.NAME: "individual",
                  EntityType.ORGANISATION: "organization"}


def _det_id(stix_type: str, value: str) -> str:
    return f"{stix_type}--{uuid.uuid5(_NS, stix_type + ':' + value.lower())}"


def to_stix_bundle(graph: InMemoryGraph) -> dict:
    objects: list[dict] = []
    id_for: dict[str, str] = {}   # entity key -> stix id
    for key, e in graph.nodes.items():
        obj = _entity_to_stix(e)
        if obj:
            id_for[key] = obj["id"]
            objects.append(obj)
    for ed in graph.edges:
        src, dst = id_for.get(ed.src_key), id_for.get(ed.dst_key)
        if src and dst:
            rid = _det_id("relationship", f"{src}|{dst}|{ed.via}")
            objects.append({"type": "relationship", "spec_version": "2.1", "id": rid,
                            "relationship_type": "related-to", "source_ref": src, "target_ref": dst,
                            "description": ed.via})
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objects}


def _entity_to_stix(e: Entity) -> dict | None:
    if e.type in _STIX_SCO:
        stix_type, _ = _STIX_SCO[e.type]
        return {"type": stix_type, "spec_version": "2.1", "id": _det_id(stix_type, e.value), "value": e.value}
    if e.type in _STIX_IDENTITY:
        sid = _det_id("identity", e.value)
        return {"type": "identity", "spec_version": "2.1", "id": sid, "name": e.value,
                "identity_class": _STIX_IDENTITY[e.type]}
    if e.type is EntityType.CVE:
        vid = _det_id("vulnerability", e.value)
        return {"type": "vulnerability", "spec_version": "2.1", "id": vid, "name": e.value,
                "external_references": [{"source_name": "cve", "external_id": e.value}]}
    return None


# --- MISP --------------------------------------------------------------------

_MISP_ATTR = {
    EntityType.EMAIL: ("email-src", "Network activity"),
    EntityType.DOMAIN: ("domain", "Network activity"),
    EntityType.IP: ("ip-dst", "Network activity"),
    EntityType.URL: ("url", "Network activity"),
    EntityType.CVE: ("vulnerability", "External analysis"),
    EntityType.PERSON: ("target-user", "Attribution"),
    EntityType.ORGANISATION: ("target-org", "Attribution"),
}


def to_misp_event(graph: InMemoryGraph, *, info: str = "Weft OSINT recon") -> dict:
    attributes: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for e in graph.nodes.values():
        mapping = _MISP_ATTR.get(e.type)
        if not mapping:
            continue
        attr_type, category = mapping
        key = (attr_type, e.value.lower())
        if key in seen:
            continue
        seen.add(key)
        attributes.append({"type": attr_type, "category": category, "value": e.value,
                           "to_ids": e.type in (EntityType.IP, EntityType.DOMAIN, EntityType.URL),
                           "comment": f"source: {e.source_module}, confidence {e.confidence:.2f}"})
    return {"Event": {"info": info, "analysis": "0", "threat_level_id": "4",
                      "distribution": "0", "Attribute": attributes}}
