# Weft

**Free-source OSINT reconnaissance aggregator.** Weft is the cross-thread that weaves
scattered open-source strands into one fabric. Give it a phone, email, username, name,
or domain, and it expands outward across free public sources, pulling back linked
entities and drawing the relationships as a graph. One query instead of twenty tabs.

Owner: HuzoSecurity Ltd. Purpose: authorised penetration-testing reconnaissance.

> **Authorised use only.** Weft aggregates information about identifiable people from open
> sources. Use it only where you hold explicit authorisation and a lawful basis. It is
> provided "AS IS", without warranty, and the authors accept no liability for misuse. See
> [DISCLAIMER.md](DISCLAIMER.md) for the full terms.

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

## Local AI (optional)

A small local model turns the raw graph into intelligence, without ever leaving the
machine. It reasons *about* the deterministic evidence; it never produces findings.

- **Report narrative.** A concise, factual summary of the graph in British English.
- **Identity assessment.** Compares the collected entities against the seed and judges
  whether they belong to one individual, listing corroborating signals and conflicts and
  ending with a confidence band. A labelled inference for a human to confirm, never an
  auto-merge and never a deterministic finding.
- **Grounded.** Any narrative that names an email or URL not present in the graph is
  discarded, so the model can summarise but cannot invent.
- **Local-only and optional.** Runs against a local Ollama (a 3B–8B model is plenty, and
  fits an 8GB GPU). Personal data never reaches a hosted model, and Weft works fully
  without it. Configure with `OLLAMA_URL` and `REASONER_MODEL`.

## Status

Phases 0–5 complete: the compliance-gated engagement model and fail-closed scope gate,
17 free-source modules across phone, email, username, name, and domain, the breadth-first
orchestrator, a Streamlit graph UI, self-hosted search and Wayback history, the local-AI
report narrator and identity assessment, and the purge/retention lifecycle. Tested
throughout.

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
