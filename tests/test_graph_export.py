"""Interactive graph export — risk emphasis (pure) + standalone HTML (pyvis)."""
from __future__ import annotations

import pytest

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.reporting.graph_export import emphasise_risk, export_interactive_graph
from weft.ui.graphview import build_vis_payload

try:
    import pyvis  # noqa: F401
    HAVE_PYVIS = True
except Exception:
    HAVE_PYVIS = False


def _g():
    g = InMemoryGraph()
    g.upsert_entity(Entity.make(EntityType.EMAIL, "rob@example.com", source_module="m", confidence=0.9, seed_id="s"))
    g.upsert_entity(Entity.make(EntityType.IP, "1.2.3.4", source_module="ip_blocklists", confidence=0.8,
                                seed_id="s", metadata={"reputation": "listed", "list_count": 3}))
    g.upsert_entity(Entity.make(EntityType.CVE, "CVE-2021-44228", source_module="cve_context", confidence=0.9,
                                seed_id="s", metadata={"known_exploited": True}))
    return g


def test_emphasise_risk_marks_only_risk_nodes():
    g = _g()
    payload = emphasise_risk(build_vis_payload(g), g)
    risk = {n["id"] for n in payload["nodes"] if n.get("risk")}
    assert "ip:1.2.3.4" in risk
    assert "cve:cve-2021-44228" in risk
    assert "email:rob@example.com" not in risk        # a clean node is not marked
    for n in payload["nodes"]:
        if n.get("risk"):
            assert isinstance(n["color"], dict) and n["color"]["border"] == "#dc2626"


@pytest.mark.skipif(not HAVE_PYVIS, reason="pyvis not importable in this interpreter")
def test_export_interactive_graph_has_title_and_legend():
    html = export_interactive_graph(_g(), title="Case 42")
    assert "Case 42" in html
    assert "risk (sanctions / malware / known-exploited)" in html   # legend present
    assert "vis-network" in html or "drawGraph" in html or "network" in html.lower()
