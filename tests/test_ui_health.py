"""UI live-status checks."""
from __future__ import annotations

from weft.ui import health


def test_service_status_shape():
    st = health.service_status()
    assert set(st) == {"Neo4j", "SearXNG", "Tor", "Ollama"}
    assert all(isinstance(v, bool) for v in st.values())


def test_port_open_false_on_closed_port():
    assert health.port_open(1, timeout=0.2) is False   # port 1 is not listening


def test_all_live_logic():
    assert health.all_live({"a": True, "b": True}) is True
    assert health.all_live({"a": True, "b": False}) is False
    assert health.all_live({}) is False
