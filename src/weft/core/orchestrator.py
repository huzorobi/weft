"""The orchestrator: breadth-first seed expansion.

Given one or more authorised seeds, it expands outward across enabled modules,
writing entities and relationships into the graph and logging every call.

Flow, per the build brief:
  * The scope gate runs on each SEED before anything else. A refused seed is audited
    and dropped; only allowed seeds are expanded. (Discovered entities are the natural
    expansion of an authorised seed and are not re-gated; the depth cap bounds them.)
  * A queue of unprocessed entities plus a ``seen`` set. Pop an entity, find every
    enabled module whose ``accepts`` includes its type and whose ToS opt-in is
    satisfied, run them with per-module rate limiting and a timeout, write new entities
    and links, enqueue new ones if under the depth cap.
  * A module is health-checked once per run; if it is down (missing binary/free key,
    dead endpoint) it is skipped for the whole run and the skip is audited, so a dead
    source never looks like a clean "no results".
  * Stop when the queue empties or the depth cap is hit.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

from weft.compliance.audit import AuditLogger
from weft.compliance.engagement import Engagement, GateOutcome, LegalAcceptance, ScopeGate, ScopeOverride
from weft.core.entity import Entity
from weft.core.graphstore import GraphStore
from weft.core.module import Module, RunContext


@dataclass
class RunResult:
    engagement_id: str | None
    seeds_allowed: list[str] = field(default_factory=list)
    seeds_refused: list[str] = field(default_factory=list)
    entities: dict[str, Entity] = field(default_factory=dict)  # key -> entity as last written
    module_calls: int = 0
    modules_skipped: dict[str, str] = field(default_factory=dict)  # module -> reason
    errors: list[str] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return len(self.entities)


class Orchestrator:
    def __init__(
        self,
        *,
        modules: list[Module],
        graph: GraphStore,
        audit: AuditLogger,
        rate_limiter,
        secrets=None,
        http=None,
        gate: ScopeGate | None = None,
        depth_cap: int = 2,
    ):
        self._modules = modules
        self._graph = graph
        self._audit = audit
        self._rate = rate_limiter
        self._secrets = secrets
        self._http = http
        self._gate = gate or ScopeGate()
        self._depth_cap = depth_cap

    async def run(
        self,
        seeds: list[Entity],
        *,
        engagement: Engagement | None,
        acceptance: LegalAcceptance | None,
        operator: str,
        allow_tos_risk: bool = False,
        override: ScopeOverride | None = None,
    ) -> RunResult:
        result = RunResult(engagement_id=engagement.id if engagement else None)
        queue: deque[tuple[Entity, int]] = deque()
        seen: set[str] = set()

        # Log the run configuration up front — in particular the ToS-flagged opt-in, so the
        # operator's per-run choice is on the record (a compliance requirement).
        self._audit.record(
            action="run_start", engagement_id=result.engagement_id, operator=operator,
            detail={"allow_tos_risk": allow_tos_risk, "depth_cap": self._depth_cap,
                    "seeds": [s.key() for s in seeds]},
        )

        # 1. Gate each seed. Only allowed seeds enter the queue.
        for seed in seeds:
            decision = self._gate.validate(
                engagement=engagement, seed=seed, acceptance=acceptance, override=override,
            )
            self._audit.record_gate(decision)
            if decision.allowed:
                result.seeds_allowed.append(seed.key())
                if seed.key() not in seen:
                    seen.add(seed.key())
                    self._graph.upsert_entity(seed)
                    result.entities[seed.key()] = seed
                    queue.append((seed, 0))
            else:
                result.seeds_refused.append(seed.key())

        if not queue:
            return result

        # 2. Health-check modules once; drop the dead ones for the whole run.
        live: list[Module] = []
        for module in self._modules:
            ctx = self._ctx(engagement, operator, allow_tos_risk, 0)
            health = await module.health(ctx)
            if health.ok:
                live.append(module)
            else:
                result.modules_skipped[module.name] = health.detail
                self._audit.record(
                    action="module_skip", engagement_id=result.engagement_id,
                    operator=operator, source_module=module.name,
                    detail={"reason": health.detail},
                )

        # 3. BFS expansion. depth_cap is the maximum depth of any node: an entity at
        #    the cap is recorded but not expanded, so nothing beyond the cap is created.
        while queue:
            entity, depth = queue.popleft()
            if depth >= self._depth_cap:
                continue  # boundary node — already in the graph, not expanded further
            for module in live:
                if not module.can_run(entity, allow_tos_risk=allow_tos_risk):
                    continue
                new_entities = await self._call(module, entity, engagement, operator, allow_tos_risk, depth, result)
                for child in new_entities:
                    self._graph.upsert_entity(child)
                    self._graph.link(entity, child, via=module.name, confidence=child.confidence)
                    result.entities[child.key()] = child
                    if child.key() not in seen:
                        seen.add(child.key())
                        queue.append((child, depth + 1))
        return result

    async def _call(self, module, entity, engagement, operator, allow_tos_risk, depth, result) -> list[Entity]:
        ctx = self._ctx(engagement, operator, allow_tos_risk, depth)
        self._audit.record(
            action="module_run", engagement_id=result.engagement_id, operator=operator,
            source_module=module.name, entity_key=entity.key(), detail={"depth": depth},
        )
        await self._rate.acquire(module.name)
        result.module_calls += 1
        try:
            out = await asyncio.wait_for(module.run(entity, ctx), timeout=module.timeout_s)
            return list(out or [])
        except asyncio.TimeoutError:
            msg = f"{module.name} timed out after {module.timeout_s}s on {entity.key()}"
            result.errors.append(msg)
            self._audit.record(action="module_error", engagement_id=result.engagement_id,
                                operator=operator, source_module=module.name,
                                entity_key=entity.key(), detail={"error": "timeout"})
            return []
        except Exception as exc:  # a module must never crash the run
            msg = f"{module.name} failed on {entity.key()}: {exc!r}"
            result.errors.append(msg)
            self._audit.record(action="module_error", engagement_id=result.engagement_id,
                                operator=operator, source_module=module.name,
                                entity_key=entity.key(), detail={"error": repr(exc)})
            return []

    def _ctx(self, engagement, operator, allow_tos_risk, depth) -> RunContext:
        return RunContext(
            engagement_id=engagement.id if engagement else "",
            operator=operator,
            allow_tos_risk=allow_tos_risk,
            depth=depth,
            rate_limiter=self._rate,
            secrets=self._secrets,
            audit=self._audit,
            http=self._http,
        )
