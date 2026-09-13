"""Risk & identity correlation rules — sanctions, known-exploited CVE, malicious infra, shared PGP key."""
from __future__ import annotations

from weft.core.correlation import CorrelationEngine
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph


def _e(etype, val, *, meta=None, conf=0.9, src="m"):
    return Entity.make(etype, val, source_module=src, confidence=conf, seed_id="s", metadata=meta or {})


def _find(g, rule):
    return [f for f in CorrelationEngine().run(g) if f.rule == rule]


def test_sanctions_match_surfaces():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.ORGANISATION, "BANCO NACIONAL DE CUBA", conf=0.5,
                       meta={"sanctioned": True, "list": "OFAC SDN", "programme": "CUBA"}, src="sanctions_screen"))
    f = _find(g, "sanctions_match")
    assert f and "OFAC SDN" in f[0].detail and "CUBA" in f[0].detail
    assert "sanctions_screen" in f[0].sources


def test_known_exploited_cve_surfaces_with_ransomware():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.CVE, "CVE-2021-44228",
                       meta={"known_exploited": True, "kev_name": "Log4Shell", "ransomware_use": "Known"},
                       src="cve_context"))
    f = _find(g, "known_exploited_cve")
    assert f and "Log4Shell" in f[0].detail and "ransomware" in f[0].detail.lower()
    assert f[0].confidence >= 0.9


def test_cve_not_exploited_produces_no_finding():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.CVE, "CVE-2000-0001", meta={"known_exploited": False}))
    assert _find(g, "known_exploited_cve") == []


def test_malicious_infrastructure_from_blocklists():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.IP, "1.2.3.4",
                       meta={"reputation": "listed", "on_blocklists": ["ipsum_l3"], "list_count": 3},
                       src="ip_blocklists"))
    f = _find(g, "malicious_infrastructure")
    assert f and "blocklists" in f[0].detail and "3 lists" in f[0].detail


def test_malicious_infrastructure_from_abusech_ioc():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.DOMAIN, "evil.example",
                       meta={"reputation": "malware_ioc", "malware": "Cobalt Strike"}, src="abusech"))
    f = _find(g, "malicious_infrastructure")
    assert f and "Cobalt Strike" in f[0].detail


def test_shared_pgp_key_identity_link():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.EMAIL, "torvalds@linux-foundation.org", conf=0.8,
                       meta={"linked_via": "shared PGP key", "with_email": "torvalds@kernel.org"},
                       src="pgp_keyservers"))
    f = _find(g, "shared_pgp_key")
    assert f and "torvalds@kernel.org" in f[0].detail
    assert f[0].confidence >= 0.8


def test_clean_graph_has_no_risk_findings():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.IP, "8.8.8.8", meta={"country": "US"}))
    rules = {f.rule for f in CorrelationEngine().run(g)}
    assert not ({"sanctions_match", "known_exploited_cve", "malicious_infrastructure", "shared_pgp_key"} & rules)
