"""Orchestrator: gating, BFS, dedup, depth cap, health-skip, error isolation."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from weft.compliance.audit import AuditLogger, InMemoryAuditStore
from weft.compliance.engagement import (
    LEGAL_STATEMENT_VERSION,
    Engagement,
    LegalAcceptance,
    ScopeGate,
)
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.orchestrator import Orchestrator
from weft.core.ratelimit import NoopRateLimiter

from _fakes import BoomModule, DownModule, StaticModule

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _eng():
    return Engagement(
        id="ENG-1", client="Acme", scope_ref="SOW-1", lawful_basis="LI",
        authorised_targets=["example.com"],
        start_date=date(2026, 9, 1), end_date=date(2026, 12, 31),
    )


def _accept():
    return LegalAcceptance(operator="rob", statement_version=LEGAL_STATEMENT_VERSION, accepted_at=NOW)


def _seed(v="example.com", t=EntityType.DOMAIN):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s1")


def _child(v, t=EntityType.DOMAIN):
    return Entity.make(t, v, source_module="m", confidence=0.9, seed_id="s1")


def _orchestrator(modules, depth_cap=2):
    store = InMemoryAuditStore()
    return (
        Orchestrator(
            modules=modules, graph=InMemoryGraph(),
            audit=AuditLogger(store, clock=lambda: NOW),
            rate_limiter=NoopRateLimiter(), gate=ScopeGate(clock=lambda: NOW),
            depth_cap=depth_cap,
        ),
        store,
    )


def _run(orch, seeds, **kw):
    return asyncio.run(orch.run(seeds, operator="rob", **kw))


def test_refused_seed_is_dropped_and_no_expansion():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("sub.example.com")])
    orch, _ = _orchestrator([m])
    # no acceptance -> gate refuses
    res = _run(orch, [_seed()], engagement=_eng(), acceptance=None)
    assert res.seeds_refused == ["domain:example.com"]
    assert res.seeds_allowed == []
    assert res.entity_count == 0


def test_allowed_seed_expands_one_level():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com"), _child("b.example.com")])
    orch, _ = _orchestrator([m])
    res = _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    assert res.seeds_allowed == ["domain:example.com"]
    assert "domain:a.example.com" in res.entities
    assert "domain:b.example.com" in res.entities


def test_depth_cap_stops_expansion():
    # module maps any domain to one deeper domain; with cap=1 we get seed + depth1 only.
    class Chain(StaticModule):
        async def run(self, entity, ctx):
            n = entity.value.count(".")
            return [_child(f"l{n}.{entity.value}")]

    m = Chain("chain", [EntityType.DOMAIN], [])
    orch, _ = _orchestrator([m], depth_cap=1)
    res = _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    # seed (depth0) + one discovered (depth1). Depth-2 child is written but not enqueued.
    keys = set(res.entities)
    assert "domain:example.com" in keys
    assert any(k.startswith("domain:l1.") for k in keys)
    assert not any(k.startswith("domain:l2.") for k in keys)


def test_dedup_does_not_reprocess_same_entity():
    calls = {"n": 0}

    class Counter(StaticModule):
        async def run(self, entity, ctx):
            calls["n"] += 1
            # every domain yields the SAME child -> must be processed once
            return [_child("shared.example.com")]

    m = Counter("counter", [EntityType.DOMAIN], [])
    orch, _ = _orchestrator([m], depth_cap=3)
    _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    # seed processed + shared child processed once = 2 calls, not infinite
    assert calls["n"] == 2


def test_down_module_is_skipped_and_audited():
    orch, store = _orchestrator([DownModule()])
    res = _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    assert "down" in res.modules_skipped
    assert any(e.action == "module_skip" for e in store.all())


def test_module_error_is_isolated_and_logged():
    orch, store = _orchestrator([BoomModule()])
    res = _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    assert res.errors and "kaboom" in res.errors[0]
    assert any(e.action == "module_error" for e in store.all())


def test_every_module_call_is_audited():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("x.example.com")])
    orch, store = _orchestrator([m])
    _run(orch, [_seed()], engagement=_eng(), acceptance=_accept())
    runs = [e for e in store.all() if e.action == "module_run"]
    assert runs, "expected at least one module_run audit event"
