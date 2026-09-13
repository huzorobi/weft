# Changelog

All notable changes to Weft are recorded here. Dates are ISO-8601 (UTC).

## [0.16.0] — 2026-09-13

Graph analytics — key pivots and communities.

### Added
- `core.analytics`: betweenness centrality (Brandes) ranks the gatekeeper entities that
  bridge the graph — the best pivots — and connected-component community detection groups
  the graph into its natural clusters. Pure Python over the in-memory graph, no Neo4j GDS
  plugin required. The report gains a "Graph analytics" section listing the top pivots.

## [0.15.0] — 2026-09-13

Entity resolution — identity clustering.

### Added
- `core.resolution.resolve_identities`: clusters person-identifying entities that are the
  same identity — the same handle across platforms, a handle containing a name's tokens, an
  email local-part matching a handle — and records weaker fuzzy-name matches as "possibly the
  same". Never hard-merges: it produces clusters and leads with scores, so a coincidental
  match stays visible. The report gains an "Identity clusters" section, fed to the identity
  assessment.

## [0.14.0] — 2026-09-13

Native username checker + name-to-handle generation (inspired by Obipixel's socialFIND).

### Added
- `username_check`: a built-in username checker driven by a JSON site list, using Weft's
  own async HTTP client and rate limiter — so username enumeration works with no external
  binary (maigret/sherlock become optional wideners). Given a NAME it generates candidate
  handles (firstlast, first.last, flast, ...) via `core.username_gen` and checks each;
  name-derived hits are low-confidence, flagged as candidates for the identity assessment.

## [0.13.0] — 2026-09-13

Deterministic correlation engine (the evidence layer).

### Added
- `core.correlation.CorrelationEngine`: runs rules over the collected graph to surface
  patterns — presence across platforms, a name corroborated by independent sources, a
  person tied to organisations, an email tied to accounts, a shared registrant, IP geo
  clusters, hub nodes, and multi-source anchors. Each is a `Finding` with a confidence and
  its provenance (the sources behind it). Deterministic and repeatable; the model reasons
  about these findings and never invents them.
- The report gains a "Findings (correlations)" section, and the findings are fed to the
  narrative and identity-assessment prompts as grounded evidence.

## [0.12.0] — 2026-09-13

The autonomous hunter — LLM-guided pivoting.

### Added
- `core.hunter.Hunter`: an investigator loop that reasons about the graph so far and
  chooses the highest-value pivots to run next, following leads instead of a flat sweep.
  The local model picks only from a numbered menu of REAL, valid actions (a registered
  module applied to an entity in the graph); a choice outside the menu is discarded in
  code, and the model never produces a finding. Bounded by the engagement scope, a depth
  cap, a step budget, and diminishing-returns stopping. Without a model it falls back to a
  deterministic priority, so it always works. Every decision and action is audited.
- UI: an "Autonomous hunter" toggle on the run form; the runner drives either the flat
  sweep or the hunter.

## [0.11.0] — 2026-09-13

IP geolocation and KML map export (inspired by Obipixel's traceVIEW).

### Added
- `ip_geolocation`: enriches every IP entity with country, city, coordinates, ISP, and
  ASN via the free keyless ip-api.com, and surfaces the owning organisation. The
  passive-only alternative to traceVIEW's active traceroute.
- `reporting.build_kml`: exports a Google Earth KML of the geolocated IPs. Available from
  the CLI (`weft report <id> --kml map.kml`) and as a download in the UI report section.

## [0.10.0] — 2026-09-13

Neo4j persistence, engagement-isolated.

### Added
- The graph now persists to Neo4j, scoped per engagement: nodes are keyed by
  `(engagement, key)`, so two engagements never share a node — one client's data stays
  out of another's. The run renders from memory and persists to Neo4j in one pass (a tee);
  Neo4j being unreachable falls back to in-memory only.
- `Neo4jGraph.load` reads an engagement's graph back for reporting; `purge_engagement`
  deletes it, wired into the lifecycle purge.
- CLI: `weft report <id> [--model M] [--out F]` builds the report from the persisted graph.

## [0.9.0] — 2026-09-13

Phase 6 — hardening.

### Added
- `core.secrets`: an injectable secrets provider (env, on-disk file, chained), so a vault
  can slot in without touching a module. Modules read the injected provider, never the
  environment directly. Config: `SECRETS_FILE`.
- The orchestrator logs a `run_start` audit event recording the ToS-flagged opt-in, depth
  cap, and seeds, so the operator's per-run choice is on the record.

## [0.8.0] — 2026-09-13

Phase 5 — lifecycle: purge and retention.

### Added
- `lifecycle.purge_engagement`: closes out an engagement — deletes run records and
  exported files, clears the graph, and **redacts** the personal identifier inside the
  audit log while keeping who ran what, when, and against which engagement. Redaction is
  the sanctioned lawful-erasure exception to append-only, and the purge is itself recorded
  as an audit event.
- `lifecycle.expired_engagements` / `flag_expired`: the retention job that surfaces and
  flags engagements past their end date.
- CLI: `weft retention [--flag]` and `weft purge <id> --yes` (refuses without `--yes`).

## [0.7.0] — 2026-09-13

Maximum-collection default and AI identity assessment.

### Changed
- Enumeration sources (maigret, sherlock, holehe, phoneinfoga) are ON by default in the UI
  for maximum collection via public enumeration. The choice is still logged and can be
  turned off to stay on official/free-API sources only.

### Added
- AI identity assessment in the report: the local model compares the collected entities
  against the seed and judges whether they belong to one individual, listing corroborating
  signals and conflicts and ending with a confidence band (strong/moderate/weak/insufficient).
  A labelled inference for a human to confirm, grounded (discarded if it names anything not
  in the graph), never an auto-merge and never a deterministic finding.

## [0.6.0] — 2026-09-13

Report narration with a local AI, and social-presence grouping.

### Added
- `core.reasoner`: a local-only reasoning abstraction (`Reasoner` protocol, `NullReasoner`
  fallback, `OllamaReasoner`). The model narrates the graph; it never produces findings,
  and nothing leaves the estate.
- `reporting.build_report`: per-engagement Markdown report — header with the compliance
  artefacts, summary, social presence grouped by platform, full entity inventory with
  sources and confidence, and a coverage note. When a local model is available it adds a
  grounded prose narrative, discarded if it names any email/URL not in the graph.
- `reporting.classify_platform`: label a profile URL (Facebook, X, LinkedIn, GitHub,
  Instagram, Reddit, …) from open enumeration, not platform scraping.
- UI: a Report section that generates and downloads the report, with an optional local model.
- Config: `OLLAMA_URL`, `REASONER_MODEL` (small model, 8GB-GPU friendly).

## [0.5.0] — 2026-09-13

Phase 4 — search + historical.

### Added
- `search_footprint`: web footprint via a self-hosted SearXNG instance (phone/email/
  name/username -> pages that mention the seed). Self-disables if SearXNG is unreachable.
- `wayback`: historical URLs and old subdomains from the Wayback Machine CDX API.
- `phoneinfoga`: phone OSINT footprint via the external tool, intrusive scanner off.

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
