"""KML export of the geolocated IPs — a Google Earth map, inspired by traceVIEW.

Each IP entity that carries coordinates (from the ip_geolocation module) becomes a
Placemark. Open the file in Google Earth or any KML viewer. Pure and deterministic.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from weft.core.entity import EntityType
from weft.core.graphstore import InMemoryGraph


def build_kml(graph: InMemoryGraph, *, title: str = "Weft — geolocated IPs") -> str:
    placemarks: list[str] = []
    for e in graph.nodes.values():
        if e.type is not EntityType.IP:
            continue
        md = e.metadata if isinstance(e.metadata, dict) else {}
        lat, lon = md.get("lat"), md.get("lon")
        if lat is None or lon is None:
            continue
        where = ", ".join(x for x in (md.get("city"), md.get("region"), md.get("country")) if x)
        owner = " | ".join(x for x in (md.get("isp"), md.get("org"), md.get("asn")) if x)
        desc = " | ".join(x for x in (where, owner) if x)
        placemarks.append(
            "    <Placemark>\n"
            f"      <name>{escape(e.value)}</name>\n"
            f"      <description>{escape(desc)}</description>\n"
            f"      <Point><coordinates>{float(lon)},{float(lat)},0</coordinates></Point>\n"
            "    </Placemark>"
        )
    body = "\n".join(placemarks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(title)}</name>\n"
        f"{body}\n"
        "  </Document>\n"
        "</kml>\n"
    )


def has_geolocated_ips(graph: InMemoryGraph) -> bool:
    return any(
        e.type is EntityType.IP and isinstance(e.metadata, dict)
        and e.metadata.get("lat") is not None and e.metadata.get("lon") is not None
        for e in graph.nodes.values()
    )
