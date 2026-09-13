# Weft

**Free-source OSINT reconnaissance aggregator.** Weft is the cross-thread that weaves
scattered open-source strands into one fabric. Give it a domain, email, username, name,
phone, crypto address, or CVE, and it expands outward across free public sources, pulling
back linked entities and drawing the relationships as a graph. One query instead of twenty
tabs.

Owner: HuzoSecurity Ltd. Purpose: authorised penetration-testing reconnaissance.

> **Authorised use only.** Weft aggregates information about identifiable people from open
> sources. Use it only where you hold explicit authorisation and a lawful basis. It is
> provided "AS IS", without warranty, and the authors accept no liability for misuse. See
> [DISCLAIMER.md](DISCLAIMER.md) for the full terms.

## Principles

- **Free sources only.** No paid APIs, ever. Free-tier keys that cost nothing are fine, and
  every keyed source self-disables (loudly) until its key is present.
- **Passive only.** Weft reads public indexes and open data. It never attacks, scans,
  exploits, brute-forces, or logs in to a target, and it never touches private data.
- **Fail closed.** The operator accepts the terms once at launch (UK GDPR / DPA, EU GDPR, and
  US law incl. the CFAA), recorded with name, version and timestamp. The scope gate then binds
  every run in code — nothing touches a target that is not authorised.
- **Deterministic first.** The modules and correlation rules produce evidence; the local model
  only reasons *about* that evidence. The AI never invents a finding.
- **Append-only audit.** Every module call and gate decision is logged. Purge removes personal
  data and findings; the audit metadata is retained.

## What it collects — 60 modules

Every registered module is wired to the run path and health-checked; one that cannot run
(missing key, missing binary, unreachable service) reports why rather than silently doing
nothing. Seventeen entity types flow through the graph (domain, email, username, name, person,
organisation, phone, IP, URL, social profile, address, crypto address, CVE, package, archive
snapshot, breach, image).

- **Domain / infrastructure** — certificate transparency (crt.sh, certspotter), passive DNS
  and subdomains (subdomain.center, HackerTarget), RDAP/WHOIS, ARIN, Common Crawl, Wayback,
  urlscan, GitHub code/commit search, email-auth (SPF/DMARC/DKIM) spoofability.
- **Identity** — GLEIF, Wikidata, Gravatar, Keybase, PGP keyservers, Hacker News, npm,
  Stack Overflow, Bluesky (AT Protocol), username enumeration (maigret/sherlock/holehe),
  Companies House and its beneficial-ownership (PSC) register.
- **IP** — geolocation, RIPEstat, ARIN, Shodan InternetDB (keyless), threat blocklists,
  malware-filtering DNS reputation.
- **People / companies** — GDELT (global news), CourtListener (US case law), Crossref
  (publications), Apple App Store (published apps), SEC EDGAR, sanctions screening (OFAC + UN).
- **Crypto** — Bitcoin (mempool.space, keyless), ENS name↔address, Etherscan.
- **Vulnerability** — a CVE is enriched with CISA KEV (known-exploited, ransomware use) and
  OSV; a package (npm/PyPI) chains through to its CVEs and its maintainers' identities.
- **Threat** — abuse.ch (ThreatFox/URLhaus), AbuseIPDB, IP blocklists, DNS-filter reputation.
- **Dark web (opt-in)** — a passive Ahmia index search over Tor. Search-only; it never crawls
  onion content, needs a running Tor SOCKS proxy, and self-disables otherwise.
- **Free-key providers** — AbuseIPDB, Hunter.io, SecurityTrails, Etherscan, abuse.ch, and
  more behind one pluggable base; each self-disables until you add its free key to `.env`.

## Analysis

- **Correlation engine.** Deterministic rules over the graph surface patterns — the same handle
  across platforms, a name corroborated by independent sources, a person tied to organisations,
  IP clusters, hub nodes — plus risk findings: sanctions matches, known-exploited CVEs, and
  malicious infrastructure.
- **Identity resolution.** Clusters the entities that are the same person, on shared handles,
  matching name tokens, and (highest certainty) a shared PGP key. Confidence reflects how many
  independent sources corroborate a handle, not how many guessed variations share it. It never
  hard-merges — it records explainable clusters.
- **Graph analytics.** Betweenness centrality finds the best pivots; community detection groups
  connected clusters.
- **Autonomous hunter (optional).** A local model chooses the highest-value pivots from a
  validated action catalogue and follows leads instead of a flat sweep; an off-menu action is
  refused in code.
- **Priority alerts + Admiralty grading.** A ranked triage banner (sanctions and known-exploited
  CVEs as critical, malicious infrastructure and strong identity clusters as high, the top pivot
  as notable), and every entity carries its NATO Admiralty code (source reliability A–F,
  information credibility 1–6).

## Local AI (optional)

A small local model turns the graph into intelligence without ever leaving the machine. It
reasons *about* the deterministic evidence; it never produces findings.

- **Report narrative** — a concise, factual British-English summary of the graph.
- **Identity assessment** — judges whether the collected entities belong to one individual,
  listing corroborating signals and conflicts, ending with a confidence band. A labelled
  inference for a human to confirm, never an auto-merge.
- **Grounded** — any narrative that names an email or URL not in the graph is discarded, so the
  model can summarise but cannot invent.
- **Local-only** — runs against a local Ollama (a 3B–8B model is plenty, fits an 8GB GPU).
  Personal data never reaches a hosted model. Configure with `OLLAMA_URL` and `REASONER_MODEL`.

## Reports & export

- **Report** in Markdown, styled **HTML**, and **PDF** (WeasyPrint) — Priority alerts, Risk &
  exposure, findings, AI narrative and identity assessment, identity clusters, graph analytics,
  timeline, and the full entity inventory with Admiralty grades. Saved to `~/weft-reports/<id>/`.
- **Interactive graph** — a standalone pyvis page with a legend and risk nodes highlighted.
- **STIX 2.1** bundle and **MISP** event for OpenCTI / MISP interop.
- **KML** map of geolocated IPs and addresses.
- **Differential runs** — Weft persists a graph per engagement (Neo4j), so a re-run diffs
  against the last: what is new, gone, or gained confidence. A monitoring tool.

## Run

One click cold-starts everything and opens the app:

```bash
./weft.sh                 # brings up Neo4j / SearXNG / Tor + local AI, then the Streamlit UI
./weft.sh --stop          # stop the UI and the stack
```

On Linux desktops the double-clickable `weft.desktop` launcher (with the woven Weft icon)
opens Weft in a frameless Chromium app window. The UI shows live service-status dots with
restart / shutdown controls, a one-time terms screen, an always-visible search form, and
report downloads. Add free keys in `.env` (see `.env.example`) to light up the keyed sources.

## Develop

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                    # 300+ tests, deterministic and offline
```

## License

Proprietary. Copyright © 2026 HuzoSecurity Ltd. All rights reserved. The source is public
for reference only; use requires the Owner's written permission. See [LICENSE](LICENSE) and
[DISCLAIMER.md](DISCLAIMER.md).
