"""The autonomous hunter: an LLM-guided pivot loop over the graph.

Where the orchestrator does a flat breadth-first sweep (run every applicable module on
every entity up to a depth cap), the hunter *reasons about* the graph so far and chooses
the highest-value pivots to run next — following a lead like a real investigator, going
deep on a promising node instead of wide on everything.

The model's role is strictly bounded: each step it is handed a numbered menu of REAL,
valid actions (a registered module applied to an entity already in the graph) and it
picks which to run next, or signals stop. It cannot invent an action — a choice outside
the menu is discarded in code — and it never produces a finding; the deterministic
modules do. Without a model the hunter falls back to a deterministic priority, so it
always works. Everything stays inside the engagement scope, a depth cap, a step budget,
and the audit log.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from weft.compliance.audit import AuditLogger
from weft.compliance.engagement import Engagement, LegalAcceptance, ScopeGate, ScopeOverride
from weft.core.entity import Entity
from weft.core.graphstore import GraphStore
from weft.core.module import Module, RunContext
from weft.core.reasoner import NullReasoner, Reasoner


@dataclass
class HunterStep:
    step: int
    ran: list[tuple[str, str]]          # (module, entity_key)
    new_entities: int
    rationale: str


@dataclass
class HunterResult:
    engagement_id: str | None
    entities: dict[str, Entity] = field(default_factory=dict)
    steps: list[HunterStep] = field(default_factory=list)
    actions_run: int = 0
    stopped_reason: str = ""
    seeds_refused: list[str] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return len(self.entities)


@dataclass
class _Candidate:
    module: Module
    entity: Entity
    depth: int


class Hunter:
    def __init__(
        self,
        *,
        modules: list[Module],
        graph: GraphStore,
        audit: AuditLogger,
        rate_limiter,
        secrets=None,
        http=None,
        reasoner: Reasoner | None = None,
        gate: ScopeGate | None = None,
        max_depth: int = 4,
        max_steps: int = 20,
        actions_per_step: int = 4,
        max_entities: int = 250,
    ):
        self._modules = modules
        self._graph = graph
        self._audit = audit
        self._rate = rate_limiter
        self._secrets = secrets
        self._http = http
        self._reasoner = reasoner or NullReasoner()
        self._gate = gate or ScopeGate()
        self._max_depth = max_depth
        self._max_steps = max_steps
        self._per_step = actions_per_step
        self._max_entities = max_entities

    async def run(
        self,
        seeds: list[Entity],
        *,
        engagement: Engagement | None,
        acceptance: LegalAcceptance | None,
        operator: str,
        allow_tos_risk: bool = False,
        override: ScopeOverride | None = None,
    ) -> HunterResult:
        result = HunterResult(engagement_id=engagement.id if engagement else None)
        depth: dict[str, int] = {}
        entities: dict[str, Entity] = {}

        self._audit.record(action="hunter_start", engagement_id=result.engagement_id, operator=operator,
                           detail={"allow_tos_risk": allow_tos_risk, "max_depth": self._max_depth,
                                   "max_steps": self._max_steps})

        # gate each seed; only allowed seeds enter the graph
        for seed in seeds:
            decision = self._gate.validate(engagement=engagement, seed=seed, acceptance=acceptance, override=override)
            self._audit.record_gate(decision)
            if decision.allowed:
                self._graph.upsert_entity(seed)
                entities[seed.key()] = seed
                depth[seed.key()] = 0
            else:
                result.seeds_refused.append(seed.key())
        if not entities:
            result.stopped_reason = "no authorised seed"
            result.entities = entities
            return result

        live = await self._live_modules(engagement, operator, allow_tos_risk)
        done: set[tuple[str, str]] = set()
        stalls = 0

        for step_no in range(1, self._max_steps + 1):
            candidates = self._candidates(entities, depth, live, allow_tos_risk, done)
            if not candidates:
                result.stopped_reason = "no further pivots"
                break

            chosen, stop, rationale = self._prioritise(candidates, entities)
            if stop:
                result.stopped_reason = "model judged the investigation complete"
                self._audit.record(action="hunter_stop", engagement_id=result.engagement_id,
                                   operator=operator, detail={"rationale": rationale[:300]})
                break

            ran: list[tuple[str, str]] = []
            new_count = 0
            for cand in chosen[: self._per_step]:
                done.add((cand.module.name, cand.entity.key()))
                children = await self._call(cand.module, cand.entity, engagement, operator,
                                            allow_tos_risk, cand.depth, result)
                ran.append((cand.module.name, cand.entity.key()))
                for child in children:
                    self._graph.upsert_entity(child)
                    self._graph.link(cand.entity, child, via=cand.module.name, confidence=child.confidence)
                    if child.key() not in entities and len(entities) < self._max_entities:
                        entities[child.key()] = child
                        depth[child.key()] = min(depth.get(cand.entity.key(), 0) + 1, self._max_depth)
                        new_count += 1
                    else:
                        entities[child.key()] = child

            result.steps.append(HunterStep(step_no, ran, new_count, rationale[:200]))
            self._audit.record(action="hunter_step", engagement_id=result.engagement_id, operator=operator,
                               detail={"step": step_no, "ran": [f"{m}:{k}" for m, k in ran],
                                       "new_entities": new_count, "rationale": rationale[:200]})
            stalls = stalls + 1 if new_count == 0 else 0
            if stalls >= 2:
                result.stopped_reason = "no new entities (diminishing returns)"
                break
        else:
            result.stopped_reason = "step budget reached"

        result.entities = entities
        return result

    # ------------------------------------------------------------------ helpers

    async def _live_modules(self, engagement, operator, allow_tos_risk) -> list[Module]:
        live = []
        for module in self._modules:
            health = await module.health(self._ctx(engagement, operator, allow_tos_risk, 0))
            if health.ok:
                live.append(module)
            else:
                self._audit.record(action="module_skip", engagement_id=engagement.id if engagement else None,
                                   operator=operator, source_module=module.name, detail={"reason": health.detail})
        return live

    def _candidates(self, entities, depth, live, allow_tos_risk, done) -> list[_Candidate]:
        out: list[_Candidate] = []
        for key, entity in entities.items():
            d = depth.get(key, 0)
            if d >= self._max_depth:
                continue
            for module in live:
                if not module.can_run(entity, allow_tos_risk=allow_tos_risk):
                    continue
                if (module.name, key) in done:
                    continue
                out.append(_Candidate(module, entity, d))
        return out

    def _prioritise(self, candidates: list[_Candidate], entities) -> tuple[list[_Candidate], bool, str]:
        """Let the model pick the next pivots from the real menu; fall back to a deterministic priority."""
        deterministic = sorted(
            candidates, key=lambda c: (c.module.reliability, c.entity.confidence, -c.depth), reverse=True)
        if not self._reasoner.available:
            return deterministic, False, "deterministic priority (no model)"

        menu = deterministic[:30]
        listing = "\n".join(
            f"{i}: run '{c.module.name}' on {c.entity.type.value} \"{c.entity.value[:60]}\""
            for i, c in enumerate(menu))
        by_type: dict[str, int] = {}
        for e in entities.values():
            by_type[e.type.value] = by_type.get(e.type.value, 0) + 1
        summary = ", ".join(f"{t}: {n}" for t, n in sorted(by_type.items()))
        system = (
            "You are an OSINT investigator choosing the next pivots for an authorised engagement. "
            "From the NUMBERED candidate actions, pick up to 4 indices that best advance identifying and "
            "enriching the subject (favour turning a discovered username or email into profiles, a domain into "
            "subdomains, an IP into its owner; avoid low-value repeats). Reply ONLY with JSON: "
            '{"run": [<indices>], "stop": <bool>, "why": "<one line>"}. Use ONLY indices from the list. '
            "Set stop=true only when further pivots would add little.")
        prompt = f"Graph so far: {summary}.\nCandidate actions:\n{listing}"
        raw = self._reasoner.narrate(system=system, prompt=prompt)
        idxs, stop, why = _parse_choice(raw, len(menu))
        if not idxs and not stop:
            return deterministic, False, "deterministic priority (unparseable model reply)"
        chosen = [menu[i] for i in idxs]
        return chosen, stop, why or "model-selected pivots"

    async def _call(self, module, entity, engagement, operator, allow_tos_risk, depth, result) -> list[Entity]:
        ctx = self._ctx(engagement, operator, allow_tos_risk, depth)
        self._audit.record(action="module_run", engagement_id=result.engagement_id, operator=operator,
                           source_module=module.name, entity_key=entity.key(), detail={"depth": depth, "hunter": True})
        await self._rate.acquire(module.name)
        result.actions_run += 1
        try:
            out = await asyncio.wait_for(module.run(entity, ctx), timeout=module.timeout_s)
            return list(out or [])
        except asyncio.TimeoutError:
            self._audit.record(action="module_error", engagement_id=result.engagement_id, operator=operator,
                               source_module=module.name, entity_key=entity.key(), detail={"error": "timeout"})
            return []
        except Exception as exc:  # a module never crashes the hunt
            self._audit.record(action="module_error", engagement_id=result.engagement_id, operator=operator,
                               source_module=module.name, entity_key=entity.key(), detail={"error": repr(exc)})
            return []

    def _ctx(self, engagement, operator, allow_tos_risk, depth) -> RunContext:
        return RunContext(
            engagement_id=engagement.id if engagement else "", operator=operator,
            allow_tos_risk=allow_tos_risk, depth=depth, rate_limiter=self._rate,
            secrets=self._secrets, audit=self._audit, http=self._http)


def _parse_choice(raw: str, n: int) -> tuple[list[int], bool, str]:
    """Parse the model's {run, stop, why} reply leniently and validate indices are in range."""
    if not raw:
        return [], False, ""
    stop = bool(re.search(r'"stop"\s*:\s*true', raw, re.I))
    why = ""
    m = re.search(r'"why"\s*:\s*"([^"]*)"', raw, re.I)
    if m:
        why = m.group(1)
    idxs: list[int] = []
    try:
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        run = obj.get("run", [])
        idxs = [int(i) for i in run if isinstance(i, (int, float)) and 0 <= int(i) < n]
        stop = bool(obj.get("stop", stop))
        why = obj.get("why", why)
    except Exception:
        # fall back to scraping the first bracketed list of numbers
        m = re.search(r'"run"\s*:\s*\[([0-9,\s]*)\]', raw)
        if m:
            idxs = [int(x) for x in re.findall(r"\d+", m.group(1)) if 0 <= int(x) < n]
    # dedup preserve order
    seen: set[int] = set()
    idxs = [i for i in idxs if not (i in seen or seen.add(i))]
    return idxs, stop, why
