"""Report builder, platform classification, and grounded AI narration."""
from __future__ import annotations

from datetime import date

from weft.compliance.engagement import ControllerRole, Engagement
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.reasoner import NullReasoner
from weft.reporting.build import _is_grounded, build_report
from weft.reporting.platforms import classify_platform


def _eng():
    return Engagement(id="ENG-1", client="Acme", scope_ref="SOW-1", lawful_basis="LI",
                      authorised_targets=["example.com"], start_date=date(2026, 1, 1),
                      end_date=date(2026, 12, 31), dpia_ref="D1", lia_ref="L1",
                      controller_role=ControllerRole.PROCESSOR)


def _graph():
    g = InMemoryGraph()
    for etype, val, conf, src in [
        (EntityType.EMAIL, "rob@example.com", 0.9, "gravatar"),
        (EntityType.SOCIAL_PROFILE, "https://twitter.com/rob", 0.7, "gravatar"),
        (EntityType.URL, "https://github.com/rob", 0.9, "github_user"),
        (EntityType.SOCIAL_PROFILE, "https://www.linkedin.com/in/rob", 0.6, "maigret"),
        (EntityType.NAME, "Robert Huzo", 0.8, "companies_house"),
    ]:
        g.upsert_entity(Entity.make(etype, val, source_module=src, confidence=conf, seed_id="s"))
    return g


class _FakeReasoner:
    name = "fake"
    def __init__(self, text, available=True):
        self._text, self._av = text, available
    @property
    def available(self):
        return self._av
    def narrate(self, *, system, prompt):
        return self._text


# --- platform classification ---
def test_classify_platform():
    assert classify_platform("https://facebook.com/x") == "Facebook"
    assert classify_platform("https://x.com/x") == "X (Twitter)"
    assert classify_platform("https://www.linkedin.com/in/x") == "LinkedIn"
    assert classify_platform("https://github.com/x") == "GitHub"
    assert classify_platform("https://example.com/x") is None


# --- deterministic report (no LLM) ---
def test_report_deterministic_sections():
    md = build_report(_eng(), _graph(), reasoner=NullReasoner(), seeds=["rob@example.com"])
    assert "# OSINT reconnaissance report — Acme" in md
    assert "## Summary" in md
    assert "## Social presence" in md
    assert "Facebook" not in md            # no facebook entity in graph
    assert "X (Twitter)" in md and "LinkedIn" in md and "GitHub" in md
    assert "## Entities" in md
    assert "## Coverage" in md
    assert "DPIA reference:** D1" in md
    assert "No local model available" in md   # NullReasoner -> no narrative


# --- grounded narrative included ---
def test_grounded_narrative_included():
    md = build_report(_eng(), _graph(), reasoner=_FakeReasoner(
        "Robert Huzo has a GitHub presence at https://github.com/rob and an email rob@example.com."),
        seeds=["rob@example.com"])
    assert "AI-assisted summary" in md
    assert "GitHub presence" in md


# --- hallucinated narrative discarded ---
def test_hallucinated_narrative_discarded():
    md = build_report(_eng(), _graph(), reasoner=_FakeReasoner(
        "The subject also owns https://evil-invented-domain.example and secret@nowhere.test."),
        seeds=["rob@example.com"])
    assert "evil-invented-domain" not in md
    assert "grounding check" in md            # fell back to deterministic


def test_is_grounded_unit():
    by_type = {"email": [Entity.make(EntityType.EMAIL, "rob@example.com", source_module="s", confidence=1.0, seed_id="s")]}
    assert _is_grounded("Contact rob@example.com for details.", by_type)
    assert not _is_grounded("Also fake@other.com is linked.", by_type)


def test_identity_assessment_section_present_and_grounded():
    md = build_report(_eng(), _graph(), reasoner=_FakeReasoner(
        "The GitHub profile https://github.com/rob and email rob@example.com share the name Robert Huzo. "
        "Confidence: moderate."), seeds=["rob@example.com"])
    assert "## Identity assessment" in md
    assert "Confidence: moderate" in md


def test_identity_assessment_hallucination_discarded():
    md = build_report(_eng(), _graph(), reasoner=_FakeReasoner(
        "Also linked to https://made-up-site.example. Confidence: strong."), seeds=["rob@example.com"])
    assert "made-up-site" not in md
    assert "failed the grounding check" in md


def test_identity_assessment_fallback_without_model():
    md = build_report(_eng(), _graph(), reasoner=NullReasoner())
    assert "## Identity assessment" in md
    assert "No local model available for an identity assessment" in md


def test_risk_and_exposure_section_surfaces_high_stakes_signals():
    from weft.reporting.build import build_report, NullReasoner
    g = InMemoryGraph()
    g.upsert_entity(Entity.make(EntityType.CVE, "CVE-2021-44228", source_module="cve_context",
                                confidence=0.9, seed_id="s",
                                metadata={"known_exploited": True, "kev_name": "Log4Shell",
                                          "ransomware_use": "Known"}))
    g.upsert_entity(Entity.make(EntityType.ORGANISATION, "BANCO NACIONAL DE CUBA",
                                source_module="sanctions_screen", confidence=0.5, seed_id="s",
                                metadata={"sanctioned": True, "list": "OFAC SDN", "programme": "CUBA"}))
    md = build_report(_eng(), g, reasoner=NullReasoner(), seeds=["x"])
    assert "## Risk & exposure" in md
    assert "Known-exploited vulnerability" in md and "Log4Shell" in md
    assert "Sanctions" in md and "OFAC SDN" in md
    # risk section appears before the general findings list
    assert md.index("## Risk & exposure") < md.index("## Findings (correlations)")


def test_no_risk_section_when_no_high_stakes_signals():
    from weft.reporting.build import build_report, NullReasoner
    md = build_report(_eng(), _graph(), reasoner=NullReasoner(), seeds=["x"])
    assert "## Risk & exposure" not in md   # omitted when clean, to avoid implying "checked and clear"
