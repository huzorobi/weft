"""High-value alerting + Admiralty grading."""
from __future__ import annotations

from weft.core.admiralty import Admiralty, credibility_digit, grade_entity, reliability_letter
from weft.core.alerts import Alert, raise_alerts
from weft.core.correlation import Finding
from weft.core.entity import Entity, EntityType
from weft.core.resolution import IdentityCluster, Resolution


def _e(t, v, conf=0.9, src="m", meta=None):
    return Entity.make(t, v, source_module=src, confidence=conf, seed_id="s", metadata=meta or {})


# --- Admiralty ---------------------------------------------------------------

def test_reliability_letters():
    assert reliability_letter(0.95) == "A"
    assert reliability_letter(0.8) == "B"
    assert reliability_letter(0.6) == "C"
    assert reliability_letter(0.45) == "D"
    assert reliability_letter(0.2) == "E"
    assert reliability_letter(0.0) == "F"


def test_credibility_from_corroboration():
    assert credibility_digit(3, 0.5) == 1     # confirmed by other sources
    assert credibility_digit(2, 0.5) == 2     # probably true
    assert credibility_digit(1, 0.8) == 3     # possibly true
    assert credibility_digit(1, 0.5) == 4
    assert credibility_digit(1, 0.2) == 5


def test_grade_entity_uses_multi_source_metadata():
    e = _e(EntityType.NAME, "Rob Huzo", conf=0.85, meta={"sources": ["a", "b", "c"]})
    g = grade_entity(e)
    assert isinstance(g, Admiralty)
    assert g.code == "B1"   # B (0.85) + 1 (3 sources)


# --- Alerts ------------------------------------------------------------------

class _An:  # minimal analytics stub
    def __init__(self, pivots): self.pivots = pivots


def test_alerts_escalate_risk_findings_first():
    # titles as the real correlation rules emit them (each already leads with its label)
    findings = [
        Finding(rule="malicious_infrastructure", title="Malicious infrastructure: ip 1.2.3.4",
                detail="blocklists", confidence=0.8),
        Finding(rule="sanctions_match", title="Sanctions match: ACME", detail="OFAC SDN", confidence=0.5),
        Finding(rule="multi_platform_presence", title="Presence across 3 platforms", detail="y", confidence=0.6),
    ]
    alerts = raise_alerts(findings, Resolution(), _An([]))
    levels = [a.level for a in alerts]
    assert levels[0] == "critical"                       # sanctions before malicious infra
    assert any("Malicious infrastructure" in a.title for a in alerts)
    assert not any(a.title.startswith("Presence across") for a in alerts)   # non-risk finding not alerted
    # no doubled label (the fix): title should not repeat its leading phrase
    sanction = next(a for a in alerts if "Sanctions" in a.title)
    assert sanction.title == "Sanctions match: ACME"


def test_alerts_flag_strong_identity_cluster_and_pivot():
    res = Resolution(clusters=[IdentityCluster(label="rob", keys=("a", "b", "c"), confidence=0.9, basis="shared handle")])
    alerts = raise_alerts([], res, _An([("email:rob@x.com", 0.7)]))
    assert any(a.level == "high" and "identity cluster" in a.title for a in alerts)
    assert any(a.level == "notable" and "Key pivot" in a.title for a in alerts)


def test_no_alerts_on_clean_run():
    assert raise_alerts([], Resolution(), _An([])) == []
