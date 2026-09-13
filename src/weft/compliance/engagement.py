"""Engagements, the legal-acceptance gate, and the scope gate.

This is the enforcement layer. Nothing in Weft touches a source until the scope
gate returns an allowing decision. The gate is pure and offline-testable: inject the
clock and it decides from data alone, no network, no database.

Design decisions (operator, 2026-09-13):
  * Neo4j is the graph store (elsewhere); this module has no storage dependency.
  * There is no silent bypass. Before any run the operator must ACCEPT a UK-law /
    UK GDPR responsibility statement; the acceptance is recorded (operator, statement
    version, timestamp). An out-of-scope seed is refused unless that acceptance is
    present AND an explicit override with a written reason is supplied — and the
    override is logged and surfaced in the audit and report. Responsibility sits
    with the operator, on the record.
  * The Engagement carries the compliance artefacts a professional recon job needs:
    DPIA reference, LIA reference, controller/processor role, and per-domain
    verified-control proof (required before any domain-breach lookup).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

from weft.core.entity import Entity, EntityType, normalise_value

# ---------------------------------------------------------------------------
# The legal statement the operator must accept before any run. Bump the version
# whenever the wording changes; acceptances record the version they accepted, so an
# old acceptance against new wording does not silently satisfy the gate.
# ---------------------------------------------------------------------------
LEGAL_STATEMENT_VERSION = "2026-09-13.1"
LEGAL_STATEMENT = (
    "Weft processes personal data about identifiable people from open sources. "
    "Under UK law and the UK GDPR this is regulated processing even where the data "
    "is public and even where only one person uses the tool. By launching a run I "
    "confirm, as the operator, that: (a) an authorised, signed engagement is in "
    "place for this work; (b) I have a lawful basis for the processing and, where "
    "required, a completed DPIA and Legitimate Interest Assessment; (c) I will keep "
    "the processing within the engagement's authorised scope; and (d) I accept "
    "responsibility for the use of this tool and its output. No lawful basis, no run."
)


class ControllerRole(str, Enum):
    CONTROLLER = "controller"
    PROCESSOR = "processor"
    JOINT_CONTROLLER = "joint_controller"


class GateOutcome(str, Enum):
    ALLOWED = "allowed"                    # in scope, all preconditions met
    ALLOWED_OVERRIDE = "allowed_override"  # out of scope, run behind a logged override
    REFUSED = "refused"                    # fail closed


@dataclass(frozen=True)
class LegalAcceptance:
    """A record that the operator accepted the responsibility statement."""

    operator: str
    statement_version: str
    accepted_at: datetime

    def is_current(self) -> bool:
        return self.statement_version == LEGAL_STATEMENT_VERSION


@dataclass(frozen=True)
class ScopeOverride:
    """An explicit, reasoned override for an out-of-scope seed. Always logged."""

    operator: str
    reason: str
    authorised_at: datetime


@dataclass
class Engagement:
    """An authorised piece of work. No run exists outside one of these."""

    id: str
    client: str
    scope_ref: str                       # reference to the signed scope document
    lawful_basis: str
    authorised_targets: list[str]        # normalised seed values in scope
    start_date: date
    end_date: date
    # Compliance artefacts (operator decision: carry all of them).
    dpia_ref: str | None = None
    lia_ref: str | None = None
    controller_role: ControllerRole = ControllerRole.PROCESSOR
    verified_domains: dict[str, str] = field(default_factory=dict)  # domain -> control proof ref
    status: str = "active"

    def is_active(self, *, on: date | None = None) -> bool:
        on = on or datetime.now(timezone.utc).date()
        return self.status == "active" and self.start_date <= on <= self.end_date

    def covers(self, entity: Entity) -> bool:
        """True if the entity's normalised value matches an authorised target.

        Targets may be stored raw or already-normalised; we compare against both
        the raw target and the target normalised with the seed's own type, so
        ``0161 123 4567`` in the list still matches a seed normalised to E.164.
        """
        val = entity.value.strip().lower()
        for target in self.authorised_targets:
            if val == target.strip().lower():
                return True
            if val == normalise_value(entity.type, target).strip().lower():
                return True
        return False

    def controls_domain(self, domain: str) -> bool:
        """True only if the engagement carries verified control proof for this exact
        domain. Required before any domain-breach lookup (one level stricter than
        ordinary scope)."""
        d = normalise_value(EntityType.DOMAIN, domain)
        return bool(self.verified_domains.get(d))


@dataclass
class GateDecision:
    """The gate's verdict plus the audit facts it must emit."""

    outcome: GateOutcome
    reason: str
    engagement_id: str | None
    audit_events: list[dict] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.outcome in (GateOutcome.ALLOWED, GateOutcome.ALLOWED_OVERRIDE)


class ScopeGate:
    """Fail-closed gate. Pure: pass the clock in, get a decision out.

    Order of checks (each fails closed):
      1. There must be an engagement.
      2. It must be active (status + dates).
      3. The operator must have accepted the current legal statement.
      4. The seed must be in scope, OR carry an explicit reasoned override.
    Every refusal and every override is an audit event on the decision.
    """

    def __init__(self, *, clock=None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def validate(
        self,
        *,
        engagement: Engagement | None,
        seed: Entity,
        acceptance: LegalAcceptance | None,
        override: ScopeOverride | None = None,
    ) -> GateDecision:
        now = self._clock()
        base = {"seed": seed.key(), "at": now.isoformat(), "action": "scope_gate"}

        if engagement is None:
            return self._refuse(None, "no active engagement", base)

        if not engagement.is_active(on=now.date()):
            return self._refuse(
                engagement.id,
                f"engagement '{engagement.id}' is not active (status={engagement.status}, "
                f"window {engagement.start_date}..{engagement.end_date})",
                base,
                operator=acceptance.operator if acceptance else None,
            )

        if acceptance is None or not acceptance.is_current():
            got = acceptance.statement_version if acceptance else "none"
            return self._refuse(
                engagement.id,
                f"legal responsibility statement not accepted for this run "
                f"(need {LEGAL_STATEMENT_VERSION}, got {got})",
                base,
                operator=acceptance.operator if acceptance else None,
            )

        if engagement.covers(seed):
            return GateDecision(
                outcome=GateOutcome.ALLOWED,
                reason="seed in authorised scope",
                engagement_id=engagement.id,
                audit_events=[{
                    **base, "outcome": "allowed", "engagement": engagement.id,
                    "operator": acceptance.operator,
                    "legal_statement": acceptance.statement_version,
                }],
            )

        # Out of scope: allowed ONLY with an explicit, reasoned, logged override.
        if override is None or not override.reason.strip():
            return self._refuse(
                engagement.id,
                "seed is outside the engagement's authorised targets and no reasoned "
                "override was supplied",
                base,
                operator=acceptance.operator,
            )

        return GateDecision(
            outcome=GateOutcome.ALLOWED_OVERRIDE,
            reason=f"out-of-scope seed run under logged override: {override.reason}",
            engagement_id=engagement.id,
            audit_events=[{
                **base, "outcome": "allowed_override", "engagement": engagement.id,
                "operator": override.operator,
                "override_reason": override.reason,
                "override_at": override.authorised_at.isoformat(),
                "legal_statement": acceptance.statement_version,
            }],
        )

    def _refuse(self, engagement_id, reason, base, *, operator=None) -> GateDecision:
        event = {**base, "outcome": "refused", "reason": reason, "engagement": engagement_id}
        if operator:
            event["operator"] = operator
        return GateDecision(
            outcome=GateOutcome.REFUSED,
            reason=reason,
            engagement_id=engagement_id,
            audit_events=[event],
        )
