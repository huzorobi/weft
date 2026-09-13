"""The module base contract must report inability to run, not no-op silently.

Uses ``asyncio.run`` directly so the test needs no pytest-asyncio plugin.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module, RunContext


class _NeedsBinary(Module):
    name = "needs_binary"
    accepts = [EntityType.DOMAIN]
    produces = [EntityType.EMAIL]
    access = Access.OFFLINE
    requires_binary = "definitely-not-a-real-binary-xyz"

    async def run(self, entity, ctx):
        return []


class _NeedsKey(Module):
    name = "needs_key"
    accepts = [EntityType.NAME]
    produces = [EntityType.ORGANISATION]
    access = Access.FREE_API
    requires_free_key = True
    secret_env = "SOME_FREE_KEY"

    async def run(self, entity, ctx):
        return []


class _Ok(Module):
    name = "ok"
    accepts = [EntityType.EMAIL]
    produces = [EntityType.URL]
    access = Access.OFFLINE

    async def run(self, entity, ctx):
        return []


class _Secrets:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, name):
        return self._m.get(name)


def _ctx(secrets=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=1, secrets=secrets)


def test_missing_binary_reports_down():
    h = asyncio.run(_NeedsBinary().health(_ctx()))
    assert not h.ok
    assert "binary" in h.detail


def test_missing_free_key_reports_down():
    h = asyncio.run(_NeedsKey().health(_ctx(secrets=_Secrets({}))))
    assert not h.ok
    assert "free key" in h.detail


def test_present_free_key_reports_up():
    h = asyncio.run(_NeedsKey().health(_ctx(secrets=_Secrets({"SOME_FREE_KEY": "abc"}))))
    assert h.ok


def test_plain_module_is_up():
    assert asyncio.run(_Ok().health(_ctx())).ok


def test_tos_risk_gating_predicate():
    m = _Ok()
    m.tos_risk = True
    e = Entity.make(EntityType.EMAIL, "a@b.com", source_module="s", confidence=1.0, seed_id="s1")
    assert not m.can_run(e, allow_tos_risk=False)
    assert m.can_run(e, allow_tos_risk=True)
