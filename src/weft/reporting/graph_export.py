"""Export the entity graph as a standalone interactive HTML artifact.

Wraps the tested pyvis payload/renderer (``weft.ui.graphview``) into a saveable page: it adds a
title and a colour legend, and highlights risk nodes (sanctioned entities, malicious
infrastructure, known-exploited CVEs) with a red border so the graph draws the eye to what
matters. The payload emphasis is pure and testable; the render step needs pyvis.
"""
from __future__ import annotations

from weft.core.graphstore import InMemoryGraph
from weft.ui.graphview import TYPE_COLOURS, build_vis_payload, render_html

_RISK_REPUTATIONS = {"malware_ioc", "listed", "flagged"}


def _is_risk(entity) -> bool:
    md = entity.metadata if isinstance(entity.metadata, dict) else {}
    if md.get("sanctioned") or md.get("reputation") in _RISK_REPUTATIONS:
        return True
    return entity.type.value == "cve" and bool(md.get("known_exploited"))


def emphasise_risk(payload: dict, graph: InMemoryGraph) -> dict:
    """Give risk nodes a red border. Returns the same payload for chaining."""
    for node in payload["nodes"]:
        entity = graph.nodes.get(node["id"])
        if entity is not None and _is_risk(entity):
            node["borderWidth"] = 4
            node["color"] = {"background": node.get("color", "#94a3b8"), "border": "#dc2626"}
            node["risk"] = True
    return payload


def _legend_html() -> str:
    items = "".join(
        f'<span style="display:inline-block;margin:2px 10px 2px 0;font-size:12px">'
        f'<span style="display:inline-block;width:11px;height:11px;border-radius:50%;'
        f'background:{colour};vertical-align:middle;margin-right:4px"></span>{etype}</span>'
        for etype, colour in sorted(TYPE_COLOURS.items())
    )
    risk = ('<span style="display:inline-block;margin:2px 0;font-size:12px">'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;'
            'background:#fff;border:3px solid #dc2626;vertical-align:middle;margin-right:4px"></span>'
            'risk (sanctions / malware / known-exploited)</span>')
    return f'<div style="padding:8px 0">{items}<br>{risk}</div>'


def export_interactive_graph(graph: InMemoryGraph, *, min_confidence: float = 0.0,
                             title: str = "Weft — entity graph") -> str:
    payload = emphasise_risk(build_vis_payload(graph, min_confidence=min_confidence), graph)
    html = render_html(payload)
    header = (
        f'<div style="font:15px system-ui,sans-serif;color:#0f172a;padding:12px 16px 0">'
        f'<h2 style="margin:0 0 2px">{_escape(title)}</h2>{_legend_html()}</div>'
    )
    # inject the header just inside <body>
    return html.replace("<body>", "<body>" + header, 1) if "<body>" in html else header + html


def write_graph_html(graph: InMemoryGraph, path: str, *, min_confidence: float = 0.0,
                     title: str = "Weft — entity graph") -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(export_interactive_graph(graph, min_confidence=min_confidence, title=title))
    return path


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
