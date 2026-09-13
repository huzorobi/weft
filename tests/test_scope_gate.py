"""Phase 0 acceptance test: the scope gate must fail closed.

A gate that cannot refuse is worthless, so these tests prove refusal first and only
then prove the allow paths. No network, no database — the gate is pure and takes an
injected clock.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from weft.compliance.audit import AuditLogger, InMemoryAuditStore
from weft.compliance.engagement import (
    LEGAL_STATEMENT_VERSION,
    ControllerRole,
    Engagement,
    GateOutcome,
    LegalAcceptance,
    ScopeGate,
    ScopeOverride,
)
from weft.core.entity import Entity, EntityType

FIXED_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _clock():
    return FIXED_NOW


def _gate():
    return ScopeGate(clock=_clock)


def _engagement(**over) -> Engagement:
    kw = dict(
        id="ENG-1",
        client="Acme Ltd",
        scope_ref="SOW-2026-001",
        lawful_basis="legitimate interest",
        authorised_targets=["example.com", "+441611234567"],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 12, 31),
        dpia_ref="DPIA-1",
        lia_ref="LIA-1",
        controller_role=ControllerRole.PROCESSOR,
        verified_domains={"example.com": "TXT-proof-ref"},
        status="active",
    )
    kw.update(over)
    return Engagement(**kw)


def _acceptance(version: str = LEGAL_STATEMENT_VERSION) -> LegalAcceptance:
    return LegalAcceptance(operator="rob", statement_version=version, accepted_at=FIXED_NOW)


def _seed(value="example.com", etype=EntityType.DOMAIN) -> Entity:
    return Entity.make(etype, value, source_module="seed", confidence=1.0, seed_id="s1")


# --- fail-closed cases ------------------------------------------------------

def test_no_engagement_is_refused():
    d = _gate().validate(engagement=None, seed=_seed(), acceptance=_acceptance())
    assert d.outcome is GateOutcome.REFUSED
    assert not d.allowed
    assert "no active engagement" in d.reason


def test_inactive_engagement_is_refused():
    d = _gate().validate(engagement=_engagement(status="closed"), seed=_seed(), acceptance=_acceptance())
    assert d.outcome is GateOutcome.REFUSED
    assert "not active" in d.reason


def test_expired_engagement_is_refused():
    eng = _engagement(start_date=date(2025, 1, 1), end_date=date(2025, 2, 1))
    d = _gate().validate(engagement=eng, seed=_seed(), acceptance=_acceptance())
    assert d.outcome is GateOutcome.REFUSED


def test_missing_legal_acceptance_is_refused():
    d = _gate().validate(engagement=_engagement(), seed=_seed(), acceptance=None)
    assert d.outcome is GateOutcome.REFUSED
    assert "responsibility statement" in d.reason


def test_stale_legal_acceptance_is_refused():
    d = _gate().validate(engagement=_engagement(), seed=_seed(), acceptance=_acceptance(version="1999-old"))
    assert d.outcome is GateOutcome.REFUSED


def test_out_of_scope_without_override_is_refused():
    d = _gate().validate(engagement=_engagement(), seed=_seed("not-in-scope.net"), acceptance=_acceptance())
    assert d.outcome is GateOutcome.REFUSED
    assert "outside the engagement" in d.reason


def test_out_of_scope_with_empty_reason_override_is_refused():
    ovr = ScopeOverride(operator="rob", reason="   ", authorised_at=FIXED_NOW)
    d = _gate().validate(engagement=_engagement(), seed=_seed("nope.net"), acceptance=_acceptance(), override=ovr)
    assert d.outcome is GateOutcome.REFUSED


# --- allow paths ------------------------------------------------------------

def test_in_scope_is_allowed_and_audited():
    d = _gate().validate(engagement=_engagement(), seed=_seed(), acceptance=_acceptance())
    assert d.outcome is GateOutcome.ALLOWED
    assert d.allowed
    assert d.audit_events and d.audit_events[0]["outcome"] == "allowed"


def test_phone_normalisation_matches_scope():
    # target stored as E.164; seed given in national format must still match.
    seed = Entity.make(EntityType.PHONE, "0161 123 4567", source_module="seed", confidence=1.0, seed_id="s1")
    d = _gate().validate(engagement=_engagement(), seed=seed, acceptance=_acceptance())
    assert d.allowed, f"expected national-format phone to match E.164 target, got {d.reason}"


def test_out_of_scope_with_reasoned_override_is_allowed_and_flagged():
    ovr = ScopeOverride(operator="rob", reason="client added subsidiary domain verbally, SOW addendum pending",
                        authorised_at=FIXED_NOW)
    d = _gate().validate(engagement=_engagement(), seed=_seed("subsidiary.net"), acceptance=_acceptance(), override=ovr)
    assert d.outcome is GateOutcome.ALLOWED_OVERRIDE
    assert d.allowed
    ev = d.audit_events[0]
    assert ev["outcome"] == "allowed_override"
    assert ev["override_reason"].startswith("client added subsidiary")


# --- the decision is actually recorded in the audit log ---------------------

def test_refusal_is_written_to_the_audit_log():
    store = InMemoryAuditStore()
    logger = AuditLogger(store, clock=_clock)
    d = _gate().validate(engagement=None, seed=_seed(), acceptance=_acceptance())
    logger.record_gate(d)
    events = list(logger.events())
    assert len(events) == 1
    assert events[0].action == "scope_gate"
    assert events[0].detail["outcome"] == "refused"


def test_override_is_written_to_the_audit_log():
    store = InMemoryAuditStore()
    logger = AuditLogger(store, clock=_clock)
    ovr = ScopeOverride(operator="rob", reason="pentest of newly-acquired asset", authorised_at=FIXED_NOW)
    d = _gate().validate(engagement=_engagement(), seed=_seed("acquired.io"), acceptance=_acceptance(), override=ovr)
    logger.record_gate(d)
    events = list(logger.events())
    assert events[0].detail["outcome"] == "allowed_override"
    assert "override_reason" in events[0].detail
