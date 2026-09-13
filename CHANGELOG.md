# Changelog

All notable changes to Weft are recorded here. Dates are ISO-8601 (UTC).

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
