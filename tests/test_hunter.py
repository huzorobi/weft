"""Autonomous hunter: gating, catalogue-bounded LLM choice, deterministic fallback, budget."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from weft.compliance.audit import AuditLogger, InMemoryAuditStore
from weft.compliance.engagement import LEGAL_STATEMENT_VERSION, Engagement, LegalAcceptance, ScopeGate
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.hunter import Hunter, _parse_choice
from weft.core.ratelimit import NoopRateLimiter

from _fakes import StaticModule

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _eng():
    return Engagement(id="ENG-1", client="Acme", scope_ref="S", lawful_basis="LI",
                      authorised_targets=["example.com"], start_date=date(2026, 9, 1), end_date=date(2026, 12, 31))


def _accept():
    return LegalAcceptance(operator="rob", statement_version=LEGAL_STATEMENT_VERSION, accepted_at=NOW)


def _seed(v="example.com", t=EntityType.DOMAIN):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s1")


def _child(v, t=EntityType.DOMAIN):
    return Entity.make(t, v, source_module="m", confidence=0.9, seed_id="s1")


class _Reasoner:
    name = "fake"
    def __init__(self, reply, available=True):
        self._r, self._av = reply, available
    @property
    def available(self):
        return self._av
    def narrate(self, *, system, prompt):
        return self._r


def _hunter(modules, reasoner=None, **kw):
    store = InMemoryAuditStore()
    return Hunter(modules=modules, graph=InMemoryGraph(), audit=AuditLogger(store, clock=lambda: NOW),
                  rate_limiter=NoopRateLimiter(), reasoner=reasoner, gate=ScopeGate(clock=lambda: NOW), **kw), store


def _run(h, seeds, **kw):
    return asyncio.run(h.run(seeds, operator="rob", **kw))


# --- gate ---
def test_refused_seed_stops():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com")])
    h, _ = _hunter([m])
    res = _run(h, [_seed()], engagement=_eng(), acceptance=None)   # no acceptance -> refused
    assert res.seeds_refused == ["domain:example.com"]
    assert res.stopped_reason == "no authorised seed"


# --- deterministic (no model) expands then exhausts ---
def test_deterministic_expands_and_exhausts():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com"), _child("b.example.com")])
    h, store = _hunter([m], max_depth=2, max_steps=10)
    res = _run(h, [_seed()], engagement=_eng(), acceptance=_accept())
    assert "domain:a.example.com" in res.entities
    assert res.stopped_reason in ("no further pivots", "no new entities (diminishing returns)")
    assert any(e.action == "hunter_start" for e in store.all())
    assert any(e.action == "hunter_step" for e in store.all())


# --- model picks from the catalogue ---
def test_model_choice_runs_selected_action():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("picked.example.com")])
    h, store = _hunter([m], reasoner=_Reasoner('{"run":[0],"stop":false,"why":"pivot the domain"}'), max_steps=3)
    res = _run(h, [_seed()], engagement=_eng(), acceptance=_accept())
    assert "domain:picked.example.com" in res.entities
    assert any("pivot the domain" in s.rationale for s in res.steps)


# --- model stop is honoured ---
def test_model_stop_is_honoured():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("x.example.com")])
    h, _ = _hunter([m], reasoner=_Reasoner('{"run":[],"stop":true,"why":"enough"}'))
    res = _run(h, [_seed()], engagement=_eng(), acceptance=_accept())
    assert res.stopped_reason.startswith("model judged")
    assert res.entity_count == 1   # only the seed; nothing expanded


# --- catalogue safety: out-of-range model index cannot run an invalid action ---
def test_out_of_range_index_falls_back_not_crash():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("safe.example.com")])
    h, _ = _hunter([m], reasoner=_Reasoner('{"run":[99],"stop":false}'), max_steps=2)
    res = _run(h, [_seed()], engagement=_eng(), acceptance=_accept())
    # invalid index discarded -> deterministic fallback still runs valid actions, no crash
    assert "domain:safe.example.com" in res.entities


def test_budget_caps_steps():
    # a module that always yields a NEW deeper domain -> would run forever without the budget
    class Endless(StaticModule):
        async def run(self, entity, ctx):
            return [_child(f"n{entity.value.count('.')}.{entity.value}")]
    h, _ = _hunter([Endless("endless", [EntityType.DOMAIN], [])], max_depth=99, max_steps=3)
    res = _run(h, [_seed()], engagement=_eng(), acceptance=_accept())
    assert res.stopped_reason == "step budget reached"
    assert len(res.steps) == 3


# --- parser ---
def test_parse_choice():
    assert _parse_choice('{"run":[0,2],"stop":false,"why":"x"}', 5) == ([0, 2], False, "x")
    assert _parse_choice('{"run":[1,99],"stop":false}', 3)[0] == [1]          # out-of-range dropped
    assert _parse_choice('{"run":[],"stop":true,"why":"done"}', 3) == ([], True, "done")
    assert _parse_choice("garbage", 3) == ([], False, "")
    assert _parse_choice('noise {"run":[2],"stop":false} tail', 4)[0] == [2]  # embedded json
