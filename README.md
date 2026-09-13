# Weft

**Free-source OSINT reconnaissance aggregator.** Weft is the cross-thread that weaves
scattered open-source strands into one fabric. Give it a phone, email, username, name,
or domain, and it expands outward across free public sources, pulling back linked
entities and drawing the relationships as a graph. One query instead of twenty tabs.

Owner: HuzoSecurity Ltd. Purpose: authorised penetration-testing reconnaissance.

## Principles

- **Free sources only.** No paid APIs, ever. Free-tier keys that cost nothing are fine.
- **No lookup without an authorised engagement.** Every run attaches to an engagement
  with signed scope, lawful basis, DPIA/LIA references, and dates.
- **Fail closed.** The scope gate refuses out-of-scope seeds. There is no silent
  bypass: the operator must accept a UK-law / UK GDPR responsibility statement before
  any run, and an out-of-scope seed proceeds only behind a logged, reasoned override.
- **Append-only audit.** Every module call and gate decision is logged. Purge removes
  personal data and findings; the audit metadata is retained.
- **ToS honesty.** Scraping / unofficial-endpoint sources are flagged and off by
  default; the operator opts in per run and the choice is logged.

## Status

Phase 0 (skeleton) complete: entity model, module contract, engagement model, the
fail-closed scope gate, and the append-only audit logger, with tests.

## Develop

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Run the full stack (later phases)

```bash
cp .env.example .env      # fill in the free keys you have
docker compose up -d      # app + neo4j + postgres + searxng
```
