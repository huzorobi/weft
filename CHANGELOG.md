# Changelog

All notable changes to Weft are recorded here. Dates are ISO-8601 (UTC).

## [0.37.0] — 2026-09-13

Cryptographic identity resolution.

### Changed
- `resolve_identities` now clusters entities bound by a **shared PGP key** (from
  `pgp_keyservers`) as a high-confidence identity cluster (0.9), distinct from the heuristic
  handle/name matching. A PGP key proves control of its uids, so two emails and a name on one
  key are the same person with far more certainty than a shared handle. Still never hard-merges
  — it records an explainable cluster with its basis.

## [0.36.0] — 2026-09-13

Risk & identity correlation rules — the enrichment sources now surface as findings.

### Added
Four deterministic correlation rules so this session's enrichment signals become ranked
findings in the report and evidence for the reasoner, instead of sitting unused in metadata:
- `sanctions_match`: an entity flagged by `sanctions_screen` (OFAC/UN) becomes a finding with
  its list and programme.
- `known_exploited_cve`: a CVE marked known-exploited by `cve_context` (CISA KEV) becomes a
  high-confidence finding, noting ransomware use.
- `malicious_infrastructure`: an IP/domain flagged by `ip_blocklists`, `abusech`, or
  `dns_reputation` becomes a finding naming what flagged it.
- `shared_pgp_key`: emails/names linked by a shared PGP key (`pgp_keyservers`) become an
  identity-link finding.

## [0.35.0] — 2026-09-13

Package maintainer identity + Stack Overflow.

### Added
- `package_metadata` (PACKAGE): reads a package's registry metadata (npm and PyPI) and emits
  the author's name and email, maintainer handles, and homepage/repository links — turning a
  package into identity pivots. Repository URLs are cleaned of `git+` and `.git`. Keyless, passive.
- `stackexchange` (USERNAME / NAME / PERSON): Stack Overflow profiles matching a username or
  name, with reputation as a salience signal. Keyless (shared daily quota), passive.

## [0.34.0] — 2026-09-13

POST support + package-vulnerability chain + abuse.ch.

### Added
- HTTP client gains `post_json` (JSON or form body) — several sources are POST-only. The
  `HttpClient` protocol and the test double are updated to match.
- New `EntityType.PACKAGE`. The `npm` module now emits a PACKAGE entity (e.g. `npm:lodash`)
  for each package, alongside its URL.
- `osv_package` (PACKAGE): known vulnerabilities affecting a package from OSV.dev, emitted as
  CVE entities plus advisory links — so a developer's packages chain through to their CVEs,
  which `cve_context` then enriches with CISA KEV. Keyless, passive (POST).
- `abusech` (IP / DOMAIN): malware/C2 reputation from abuse.ch ThreatFox (IOCs) and URLhaus
  (malware URLs). Free Auth-Key, self-disables without it; POST-based.

## [0.33.0] — 2026-09-13

Free-key provider block + the keyed building block.

### Added
- `core.keyed.KeyedApiModule`: a reusable building block for free-key sources. It declares the
  key requirement and provides the key lookup and header/param helpers; the inherited health
  check reports "missing free key; module disables itself" so a keyed source never looks like a
  clean "no results". Each keyed module self-disables without its key.
- `abuseipdb` (IP): crowd-sourced IP abuse confidence, reports, and network (AbuseIPDB).
- `hunterio` (DOMAIN): corporate email addresses and the org email pattern (Hunter.io).
- `securitytrails` (DOMAIN): historical subdomains, including ones no longer live (SecurityTrails).
- `etherscan` (CRYPTO_ADDRESS): Ethereum balance and first transaction — the EVM counterpart to
  the keyless Bitcoin explorer; only fires on Ethereum-shaped addresses (Etherscan V2).
- `.env.example`: the new key names, each marked free-tier.

Endpoints were confirmed live to exist and to gate on a key (HTTP 401 without one); parse logic
is pinned by tests and will be live-verified when keys are supplied.

## [0.32.0] — 2026-09-13

Developer footprint pack.

### Added
- `hackernews` (USERNAME): resolves a username to its Hacker News profile — karma, account
  age, submissions — and extracts any links from the profile's "about" text (personal sites,
  other handles) as their own entities. Keyless, passive.
- `npm` (USERNAME): packages a developer publishes on npm, each a package page plus its source
  repository link (usually GitHub), filtered to packages the username actually
  publishes/maintains. Keyless, passive.

## [0.31.0] — 2026-09-13

Surface + footprint pack.

### Added
- `subdomain_center` (DOMAIN): subdomains from subdomain.center's index, widening coverage
  beyond CT logs and HackerTarget. Keyless, passive.
- `crossref` (NAME / PERSON / ORGANISATION): scholarly publications associated with a query
  from Crossref — DOI links with title, publisher, and year. Query matches carry modest
  confidence (a shared name is not proof of authorship). Keyless, passive.
- `apple_itunes` (ORGANISATION / NAME): apps published by an organisation via the App Store
  search API, filtered to results whose seller matches the query, yielding App Store links,
  the publisher as an organisation, and bundle IDs. Keyless, passive.

### Deferred (not shipped unverified)
- psbdmp (paste dumps) — host no longer resolves; anubis/jldc.me and openbugbounty — bot-gated
  (HTTP 403). Left rather than shipped against dead or gated endpoints.

## [0.30.0] — 2026-09-13

PGP identity + CVE context.

### Added
- New `EntityType.CVE` (seedable). `shodan_internetdb` now emits the CVEs it finds on an IP as
  CVE entities, so they can be enriched downstream.
- `pgp_keyservers` (EMAIL): looks an email up on the public PGP keyservers (keyserver.ubuntu.com,
  keys.openpgp.org, ProtonMail) and returns the real name and the other emails on the same key —
  a strong identity link — plus a Proton-account signal. Robust to malformed "email <Name>" uids.
  Keyless, passive.
- `cve_context` (CVE): enriches a CVE with CISA KEV (known-exploited, date added, ransomware use)
  and OSV.dev (summary, severity, aliases). The KEV catalogue is cached once per run. Keyless,
  passive.

## [0.29.0] — 2026-09-13

News, court records, and decentralised social.

### Added
- `gdelt` (NAME / PERSON / ORGANISATION / DOMAIN): recent worldwide news mentions from the
  GDELT DOC 2.0 API — article URLs with source, date, country, and language, over a 3-month
  window. Keyless, passive. (GDELT rate-limits to one request per 5 seconds; the module
  degrades to no results rather than erroring when throttled.)
- `courtlistener` (NAME / PERSON / ORGANISATION): US case law from CourtListener (Free Law
  Project) — the cases a subject appears in, with court and filing date. Public-domain data,
  keyless; an optional free token (COURTLISTENER_API_TOKEN) raises the rate limit.
- `bluesky` (USERNAME / NAME / PERSON): Bluesky / AT Protocol public profiles — a handle
  resolves directly (high confidence); a plain username or name searches for matching accounts
  (candidates). Public read only, no login, ToS-clean, keyless.

## [0.28.0] — 2026-09-13

Threat-intel bundles.

### Added
- `dns_reputation` (DOMAIN): resolves a domain at a neutral resolver (Google) and at public
  malware-filtering resolvers (Cloudflare Family, AdGuard) over DNS-over-HTTPS; when the
  neutral resolver returns a real address but a filter sinkholes or NXDOMAINs it, the domain
  is flagged with the providers that blocked it. Passive (queries public resolvers, never the
  domain); keyless. A flag is a lead, not proof — filters over-block.
- `ip_blocklists` (IP): checks an IP against several keyless, commercial-clean threat
  blocklists (IPsum level 3, blocklist.de, CINS Army, GreenSnow, Spamhaus DROP) and reports
  which list it, scaling confidence with the number of hits. Bulk lists are downloaded and
  cached once per run; CIDR lists (DROP) are matched by network membership. Passive.

## [0.27.0] — 2026-09-13

Infrastructure-pivot pack.

### Added
- `arin_rdap` (IP): North-American IP registration via ARIN RDAP — registrant organisation,
  network name, CIDR, allocation type, and abuse/network contact emails. Complements the
  RIPE-only `ripestat`. Keyless, passive.
- `hackertarget` (IP / DOMAIN): two pivots from HackerTarget's keyless API — reverse IP
  (an IP to the other domains co-hosted on it) and host search (a domain to its subdomains
  and their IPs). Passive (HackerTarget does the lookup; Weft reads the result). Handles the
  free-tier rate-limit body gracefully.

### Deferred (not shipped unverified)
- BGPView (keyless ASN/prefix API) was unreachable at build time (host did not resolve /
  connect); left out rather than shipped against a dead endpoint. ASN is partly covered by
  `ripestat` and now ARIN.
- spyonweb reverse-analytics needs a key (and was unreachable); favicon-hash pivoting needs
  either an active favicon fetch from the target or a Shodan key — both out of the keyless,
  passive-only scope for now.

## [0.26.0] — 2026-09-13

Sanctions & ownership pack.

### Added
- `sanctions_screen` (NAME / PERSON / ORGANISATION): screens against the OFAC SDN list (US
  Treasury) and the UN consolidated list — both public-domain, keyless. Downloads and caches
  each bulk list once per run, then matches locally on significant name tokens (particles and
  company suffixes dropped; a lone common token cannot bridge two names). A hit is labelled a
  *potential* match with its sanctioning programme, reference, and aliases, for an analyst to
  confirm — never asserted as a verdict.
- `companies_house_psc` (ORGANISATION with a Companies House number): UK beneficial ownership
  from the Persons with Significant Control register — the people and legal entities that
  ultimately own or control a company. Reuses the free Companies House key and self-disables
  without it.

### Deferred (not shipped unverified)
- The trade.gov Consolidated Screening List (OFAC+EU+UN+UK in one query) needs a free
  api.data.gov key — a future keyed module can supersede the two bulk lists.
- OpenOwnership register and ICIJ Offshore Leaks expose no clean keyless passive API
  (bot-protected / bulk-download only); left for a bulk-ingest or keyed path.

## [0.25.0] — 2026-09-13

Crypto-address recon — a new entity type and pack.

### Added
- New `EntityType.CRYPTO_ADDRESS` (seedable from the UI). Ethereum addresses fold to
  lower-case for dedup; Bitcoin addresses keep case (base58/bech32 are case-sensitive).
- `blockchain_btc` (CRYPTO_ADDRESS): Bitcoin address balance, total received/sent, and
  transaction count from mempool.space, falling back to blockchain.info. Keyless, passive
  (reads a public explorer index; never touches a wallet or node). Ignores non-BTC addresses.
- `ens_resolve` (CRYPTO_ADDRESS / USERNAME / DOMAIN): Ethereum Name Service both ways — an
  ETH address to its primary ENS name (an identity pivot), and a `.eth` name to its address.
  Keyless, passive.
- A dependency-free chain classifier so each module fires only on its own chain.

CryptoScamDB was evaluated for scam-address reports but its API is down (HTTP 502); deferred
rather than shipped unverified.

## [0.24.0] — 2026-09-13

Four keyless, verified OSINT sources.

### Added
- `ripestat` (IP): RIPE NCC open data — network abuse contact (EMAIL) and announcing
  ASN (ORGANISATION) for an IP. Authoritative, open, commercial use permitted, no key.
- `shodan_internetdb` (IP): Shodan's pre-scanned host view — open ports, CPEs, known CVEs,
  tags, and reverse-DNS hostnames (DOMAIN). Passive (reads Shodan's index, never touches
  the target); distinct from the paid Shodan API. Keyless.
- `keybase` (USERNAME): cryptographically verified social proofs — the Twitter/GitHub/etc.
  accounts a person proved they control — as high-confidence identity pivots. Keyless.
- `sec_edgar` (NAME/ORGANISATION): US corporate filings via SEC EDGAR full-text search,
  returning filer companies and their CIK. Complements the UK-only Companies House and the
  global GLEIF. Keyless (SEC requires a descriptive User-Agent, which the HTTP client sets).

All four were live-verified against the real services before shipping.

## [0.23.0] — 2026-09-13

Address geocoding and addresses on the map.

### Added
- `nominatim`: geocodes an address (from Companies House, GLEIF, or WHOIS) to coordinates
  via OpenStreetMap Nominatim (free, keyless, commercial use permitted under the usage
  policy). The KML map now plots geocoded addresses alongside geolocated IPs.

## [0.22.0] — 2026-09-13

Timeline.

### Added
- `reporting.build_timeline`: a chronology built from the temporal signals already in the
  graph — WHOIS registration and expiry dates, Wayback and Common Crawl capture timestamps —
  shown as a dated "Timeline" section in the report.

## [0.21.0] — 2026-09-13

Email spoofability and Common Crawl.

### Added
- `email_auth`: SPF/DMARC spoofability verdict for a domain (offline DNS) — protected,
  partial, or spoofable, with the reasons. High-signal, passive, keyless.
- `commoncrawl`: historical URLs and subdomains from the Common Crawl index (free, keyless)
  — a second historical corpus alongside the Wayback Machine.

## [0.20.0] — 2026-09-13

Commercially-clean IP geolocation.

### Changed
- `ip_geolocation` now uses ipwho.is (free, keyless, commercial use permitted) instead of
  ip-api.com, whose free tier is non-commercial only. Same enrichment (country, city,
  coordinates, ISP, ASN) and it works with no key or setup.

## [0.19.0] — 2026-09-13

Email breach exposure, and opt-in dark-web search over Tor.

### Added
- `xposedornot`: email breach-exposure check via XposedOrNot (free, keyless) — which known
  breaches an address appears in. Fills the gap left when HIBP's email lookup went paid.
- `darkweb_ahmia`: dark-web SEARCH via the Ahmia index over Tor — finds .onion sites that
  mention the seed. Search-only (it does not crawl .onion content). Double-gated: a
  `dark_web` module behind a new `allow_dark_web` opt-in toggle, and it self-disables unless
  a Tor SOCKS proxy is reachable. Handles Ahmia's per-session token/cookie flow.
- A separate `allow_dark_web` gate threaded through the orchestrator, hunter, runner, and UI,
  logged at run start. `dark_web` flag on the module contract.

## [0.18.0] — 2026-09-13

Keyless identity sources: GLEIF and Wikidata.

### Added
- `gleif`: global legal-entity lookup via the GLEIF LEI API (free, keyless) — matching
  organisations with their LEI and registered address, worldwide (complements the UK-only
  Companies House).
- `wikidata`: structured identity via Wikidata (free, keyless) — anchors a notable person or
  organisation to its entity, official website, and external identifiers (e.g. GitHub).

## [0.17.0] — 2026-09-13

Infrastructure-pivot sources: urlscan.io and AlienVault OTX.

### Added
- `urlscan`: historical scans for a domain — related domains, scanned URLs, and IPs (free
  key `URLSCAN_API_KEY`; self-disables without it).
- `otx`: AlienVault OTX passive DNS for a domain or IP — resolved hostnames and their IPs
  (free key `OTX_API_KEY`; self-disables without it).

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
