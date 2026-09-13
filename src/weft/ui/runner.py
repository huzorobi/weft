"""Synchronous run service that the UI calls.

Wraps the async orchestrator so the Streamlit shell (which is synchronous) can launch
a run in one call. It builds the module set, records the operator's legal acceptance,
runs the expansion into an in-memory graph for rendering, and persists the audit trail
through the injected store. Kept free of Streamlit so it is unit-testable.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from weft.compliance.audit import AuditLogger, AuditStore, InMemoryAuditStore
from weft.compliance.engagement import (
    LEGAL_STATEMENT_VERSION,
    Engagement,
    LegalAcceptance,
    ScopeGate,
    ScopeOverride,
)
from weft.config import load_settings
from weft.core.secrets import default_secrets
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.module import Module
from weft.core.orchestrator import Orchestrator, RunResult
from weft.core.ratelimit import TokenBucketRateLimiter


@dataclass
class UiRunOutput:
    graph: InMemoryGraph
    result: RunResult
    accepted: bool
    message: str


def default_modules() -> list[Module]:
    """All registered modules. Modules missing a key/binary self-disable at health()."""
    from weft.core import registry

    registry.discover()
    return registry.instances()


def execute_run(
    *,
    engagement: Engagement,
    seed_type: EntityType,
    seed_value: str,
    operator: str,
    depth_cap: int,
    allow_tos_risk: bool,
    accepted: bool,
    audit_store: AuditStore | None = None,
    modules: list[Module] | None = None,
    override_reason: str | None = None,
) -> UiRunOutput:
    """Run one expansion. Refuses when the legal statement was not accepted."""
    graph = InMemoryGraph()
    store = audit_store or InMemoryAuditStore()
    audit = AuditLogger(store)

    if not accepted:
        return UiRunOutput(graph, RunResult(engagement_id=engagement.id), False,
                           "Run refused: the responsibility statement was not accepted.")

    now = datetime.now(timezone.utc)
    acceptance = LegalAcceptance(operator=operator, statement_version=LEGAL_STATEMENT_VERSION, accepted_at=now)
    audit.record(action="legal_accept", engagement_id=engagement.id, operator=operator,
                 detail={"statement_version": LEGAL_STATEMENT_VERSION})

    override = ScopeOverride(operator=operator, reason=override_reason, authorised_at=now) \
        if override_reason and override_reason.strip() else None

    mods = modules if modules is not None else default_modules()
    seed = Entity.make(seed_type, seed_value, source_module="seed", confidence=1.0, seed_id=str(uuid.uuid4()))

    async def _go() -> RunResult:
        http = None
        needs_http = any(getattr(m, "access", None) and m.access.value in ("free_api", "self_hosted") for m in mods)
        if needs_http:
            from weft.core.http import HttpxClient
            http = HttpxClient()
        orch = Orchestrator(
            modules=mods, graph=graph, audit=audit,
            rate_limiter=TokenBucketRateLimiter(rate=5, capacity=5),
            secrets=default_secrets(load_settings().secrets_file), http=http,
            gate=ScopeGate(), depth_cap=depth_cap,
        )
        try:
            return await orch.run([seed], engagement=engagement, acceptance=acceptance,
                                  operator=operator, allow_tos_risk=allow_tos_risk, override=override)
        finally:
            if http is not None:
                await http.aclose()

    result = asyncio.run(_go())
    if result.seeds_refused and not result.seeds_allowed:
        msg = "Seed refused by the scope gate (out of scope, or engagement inactive)."
    else:
        msg = (f"{result.entity_count} entities, {result.module_calls} calls, "
               f"{len(result.modules_skipped)} module(s) skipped.")
    return UiRunOutput(graph, result, True, msg)
