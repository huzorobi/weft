# Weft — Build Instructions

Free-source OSINT reconnaissance aggregator. Owner: HuzoSecurity Ltd. Purpose:
authorised penetration-testing reconnaissance. This is an independent project.

## What it is

A single-seed OSINT aggregator that only ever uses **free** sources. Seed a phone,
email, username, name, or domain; it expands outward across open sources (BFS), pulls
back linked entities, and draws the relationships as a graph. The value is aggregation:
sources anyone could work through by hand, run at once, in one place.

**Design rule: no paid APIs, ever.** If a source needs a credit card, it does not go
in. Free-tier keys that cost nothing are fine. Self-hosted free services (SearXNG) are
fine. Per-call billing is out by design.

## Hard constraints (enforced in code, not warnings)

1. **No lookup without an active engagement.** Every run attaches to an `Engagement`:
   client, signed scope reference, lawful basis, authorised targets, dates.
2. **Scope gating, fail closed.** The seed must be in the engagement's authorised
   targets, or it is refused. There is **no silent bypass**.
3. **Legal acceptance before any run.** The operator must accept a UK-law / UK GDPR
   responsibility statement (`compliance.engagement.LEGAL_STATEMENT`). Acceptance is
   recorded (operator, statement version, timestamp). An out-of-scope seed proceeds
   ONLY with that acceptance **and** an explicit reasoned override, which is logged and
   surfaced. Responsibility sits with the operator, on the record.
4. **Append-only audit log.** Every module call and gate decision is logged before it
   happens. This is what makes the tool defensible.
5. **No breach-dump ingestion.** No module downloads or stores bulk breach corpora.
6. **Retention and deletion.** Data is tied to its engagement. Export for the report;
   purge on close. **Purge removes personal data and findings; the audit metadata of
   who-ran-what-when is retained** under its own policy.
7. **ToS honesty.** Every module carries `tos_risk`. Scraping / unofficial-endpoint
   sources are flagged and OFF by default; the operator opts in per run, logged.

## Locked decisions (operator, 2026-09-13)

- **Graph store:** Neo4j Community. Compose = app + neo4j + postgres + searxng.
- **Out-of-scope handling:** legal-acceptance gate + hardened, logged, reasoned
  override. No silent bypass.
- **Engagement model:** carries DPIA ref, LIA ref, controller/processor role, and
  per-domain verified-control proof. Operator accepts the statement at launch.
- **Module base contract:** health(), version, timeout_s, requires_binary built in from
  the start, so an external-tool module reports inability to run instead of no-opping.

## Architecture

Orchestrator holds a queue of unprocessed entities and a `seen` set. Pop an entity,
find every enabled module that accepts its type, run them async with per-module rate
limiting, write new entities + relationships to Neo4j, enqueue new ones if under the
depth cap, log every call. Stop when the queue empties or the depth cap is hit.

## Tech stack

Python 3.12, async I/O. FastAPI + Uvicorn. In-process asyncio (no Celery in v1).
Neo4j Community (graph). Postgres / SQLite (engagements, runs, audit). Self-hosted
SearXNG (search). Streamlit + pyvis (v1 UI); React + Cytoscape (v2). Pydantic Settings.
Secrets via an injectable provider.

## Repo layout

```
src/weft/
  core/       entity.py, module.py, orchestrator.py, ratelimit.py, scoring.py
  compliance/ engagement.py (models + scope gate + legal acceptance), audit.py
  storage/    graph.py (Neo4j), meta.py (Postgres/SQLite)
  modules/    phone/ email/ username/ name/ domain/
  api/        FastAPI routes
  ui/         Streamlit app
tests/
```

Each module is self-contained and registers itself so the bus discovers it without a
central import list.

## Build plan

- **Phase 0 (done):** skeleton — Entity, Module (+ tool contract), Engagement, scope
  gate, legal acceptance, audit logger, config, Neo4j + meta stores, compose, and the
  fail-closed gate test.
- **Phase 1:** orchestrator (BFS, dedup, depth cap, rate limiter) + free offline core:
  `phonenumbers_local`, `dns_enum`, `crtsh`, `certspotter`, `rdap_whois`,
  `companies_house`, `theharvester`.
- **Phase 2:** Streamlit graph view.
- **Phase 3:** account enumeration (`maigret`, `holehe`, `gravatar`, github modules).
- **Phase 4:** SearXNG search + historical (`search_footprint`, `wayback`, `phoneinfoga`).
- **Phase 5:** reporting + lifecycle (export, purge, retention job).
- **Phase 6:** confidence-scoring tuning, ToS-flagged modules behind logged opt-in,
  test coverage, proper secrets provider.

Free offline core must be solid before search and enumeration go on top. Verify each
free endpoint still behaves as its catalogue row claims when you wire it: reading a
table is not evidence a source works. A module that imports cleanly can still no-op —
prove it live via `health()`.

## Engineering standards

Production quality only. No placeholders. Small modules, clear interfaces, dependency
injection, strong typing, tests. The gate stays pure and offline-testable: inject the
clock, decide from data. Security-sensitive code (the gate) requires negative tests —
prove it refuses.

## Non-goals

No paid API integration. No bulk breach-dump ingestion. No "find anyone" mode with no
engagement. No Truecaller/Hiya scraping. No LinkedIn/Instagram scraping beyond public
search results. Nothing that touches a target's device — passive open-source recon only.
