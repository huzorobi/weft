# Changelog

All notable changes to Weft are recorded here. Dates are ISO-8601 (UTC).

## [0.4.0] — 2026-09-13

Phase 3 — account enumeration.

### Added
- Email modules: `gravatar` (profile, linked accounts, URLs from an email hash),
  `github_email` (accounts via commit search; free token), `holehe` (which sites have
  an account; external tool, ToS-flagged).
- Username modules: `github_user` (public profile), `maigret` and `sherlock`
  (social-profile discovery; external tools, ToS-flagged).
- Domain module: `github_domain` (public code referencing the domain; free token).
- Shared GitHub auth helper. External-tool modules self-disable when their binary is
  absent; their parsers are factored out and unit-tested.

## [0.3.0] — 2026-09-13

Phase 2 — graph view.

### Added
- Streamlit UI: engagement selector and creation form, the legal-acceptance gate,
  seed input and run config (depth, ToS-flagged opt-in, out-of-scope override reason),
  the interactive graph, an entity-detail panel, a confidence filter, and the
  audit-log viewer.
- `EngagementRepository` to persist and load engagements.
- `ui.graphview`: pure vis-payload builder (colour per entity type, confidence filter
  that drops low-confidence nodes and their edges) plus a pyvis HTML renderer.
- `ui.runner.execute_run`: synchronous run service wrapping the async orchestrator,
  recording legal acceptance and persisting the audit trail.

## [0.2.0] — 2026-09-13

Phase 1 — free offline core.

### Added
- Orchestrator: breadth-first seed expansion with dedup on the entity key, a depth cap
  (max node depth), per-module token-bucket rate limiting, per-call timeouts, once-per-run
  module health checks (a down source is skipped for the whole run and the skip audited),
  and error isolation so a failing module never crashes the run.
- Module registry with self-registration via a decorator and package discovery.
- Confidence scoring: source-reliability weight plus corroboration across independent sources.
- In-memory and Neo4j graph stores behind one interface.
- Modules: phonenumbers_local, dns_enum, crtsh, certspotter, rdap_whois, companies_house,
  theharvester.
- Async HTTP client with redirect-following and a retry for flaky JSON endpoints.

## [0.1.0] — 2026-09-13

Phase 0 — skeleton.

### Added
- Entity model with normalisation (E.164 phones, lowercased emails, domains) and a
  type-scoped dedup key.
- Module base contract with tool concerns built in: `health()`, version, timeout, and a
  required-binary check, plus a dependency-injected run context.
- Engagement model carrying signed-scope reference, lawful basis, DPIA and LIA
  references, controller/processor role, and per-domain verified-control proof.
- Legal responsibility acceptance required before any run (UK law / UK GDPR), recorded
  with operator, statement version, and timestamp.
- Fail-closed scope gate: no engagement, inactive/expired engagement, missing or stale
  acceptance, or an out-of-scope seed are all refused; an out-of-scope seed proceeds
  only behind a logged, reasoned override. Pure and clock-injected.
- Append-only audit logger.
- Neo4j graph store and SQLAlchemy metadata/audit store.
- Configuration via environment/`.env`, a small CLI (`version`, `legal`), and a
  four-service docker-compose (app, Neo4j, Postgres, SearXNG).
- Test suite: 24 tests, 12 of which prove the gate fails closed.
