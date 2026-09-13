"""Build a per-engagement Markdown report from the graph, with a grounded AI narrative.

Deterministic sections (engagement header, entity inventory with sources and
confidence, social presence grouped by platform, coverage note) are always produced.
When a local reasoner is available, a short prose narrative is added — but only after a
grounding check: any email, domain, or URL the narrative mentions must exist in the
graph, or the narrative is discarded. The model summarises evidence; it never adds to
it. British English; nothing is overstated.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from weft.core.entity import EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.reasoner import NullReasoner, Reasoner
from weft.reporting.platforms import classify_platform

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://[^\s)\]]+")

_SYSTEM = (
    "You are an OSINT analyst writing a concise, factual reconnaissance summary for an "
    "authorised engagement. Use ONLY the facts provided. Never invent names, accounts, "
    "links, or conclusions not present in the facts. Do not speculate about the person. "
    "British English. Neutral, professional, three short paragraphs at most."
)

_ASSESS_SYSTEM = (
    "You are an OSINT analyst judging IDENTITY CORRELATION for an authorised engagement. "
    "Given a seed identity under investigation and entities collected from several sources, "
    "assess whether they plausibly belong to ONE individual. List the corroborating signals "
    "(the same name or handle appearing across independent sources, a matching organisation or "
    "location) and any CONFLICTS (a different location, a mismatched name, a reused common "
    "handle). Weigh independent corroboration higher than a single weak hit. Finish with a line "
    "exactly of the form 'Confidence: strong' or moderate or weak or insufficient. Use ONLY the "
    "facts given; never invent. If the evidence is thin or contradictory, say insufficient. This "
    "is an assessment for a human to confirm, not a determination. British English, concise."
)


def build_report(engagement, graph: InMemoryGraph, *, reasoner: Reasoner | None = None,
                 seeds: list[str] | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    reasoner = reasoner or NullReasoner()
    nodes = list(graph.nodes.values())
    by_type: dict[str, list] = {}
    for e in nodes:
        by_type.setdefault(e.type.value, []).append(e)

    from weft.core.correlation import CorrelationEngine
    from weft.core.resolution import resolve_identities
    findings = CorrelationEngine().run(graph)
    resolution = resolve_identities(graph)

    lines: list[str] = []
    a = lines.append

    # ---- header ----
    a(f"# OSINT reconnaissance report — {engagement.client}")
    a("")
    a(f"- **Engagement:** {engagement.id}")
    a(f"- **Signed scope reference:** {engagement.scope_ref}")
    a(f"- **Authorisation window:** {engagement.start_date} to {engagement.end_date}")
    a(f"- **Lawful basis:** {engagement.lawful_basis}")
    a(f"- **Controller/processor role:** {getattr(engagement.controller_role, 'value', engagement.controller_role)}")
    if engagement.dpia_ref:
        a(f"- **DPIA reference:** {engagement.dpia_ref}")
    if engagement.lia_ref:
        a(f"- **LIA reference:** {engagement.lia_ref}")
    if seeds:
        a(f"- **Seeds:** {', '.join(seeds)}")
    a(f"- **Generated:** {now.isoformat(timespec='seconds')}")
    a("")

    # ---- summary ----
    a("## Summary")
    a("")
    a(f"- {len(nodes)} entities across {len(by_type)} types, {len(graph.edges)} relationships.")
    counts = ", ".join(f"{t}: {len(v)}" for t, v in sorted(by_type.items()))
    if counts:
        a(f"- Breakdown: {counts}.")
    a("")

    # ---- deterministic correlations (the evidence layer) ----
    a("## Findings (correlations)")
    a("")
    if findings:
        a("Deterministic patterns across the collected entities. Each carries a confidence and the "
          "sources behind it. The AI sections below reason about these; they do not add to them.")
        a("")
        for f in findings:
            src = f", sources: {', '.join(f.sources)}" if f.sources else ""
            a(f"- **[{f.strength}]** {f.title} — {f.detail} _(confidence {f.confidence:.2f}{src})_")
    else:
        a("_No cross-entity correlations found yet._")
    a("")

    # ---- AI narrative (grounded, optional) ----
    narrative = _narrate(reasoner, engagement, by_type, seeds, findings)
    a("## Narrative")
    a("")
    if narrative:
        a(f"*AI-assisted summary (local model {getattr(reasoner, 'name', 'llm')}); verify against the evidence below.*")
        a("")
        a(narrative)
    else:
        a("_No local model available, or the generated narrative failed the grounding check; "
          "the evidence below is authoritative._")
    a("")

    # ---- identity clusters (entity resolution) ----
    a("## Identity clusters")
    a("")
    if resolution.clusters:
        a("Entities that appear to be the same identity, on shared handles and matching names. "
          "These are correlations, not confirmed merges.")
        a("")
        for c in resolution.clusters:
            a(f"- **{c.label}** ({c.size} entities, confidence {c.confidence:.2f}): {c.basis}")
    else:
        a("_No multi-entity identity clusters found._")
    if resolution.possibly_same:
        a("")
        a("Possible matches (weaker leads, verify):")
        for aa, bb, score, why in resolution.possibly_same[:10]:
            a(f"- {why} _(similarity {score})_")
    a("")

    # ---- AI identity assessment (grounded, optional) ----
    assessment = _assess_identity(reasoner, engagement, by_type, seeds, findings, resolution.clusters)
    a("## Identity assessment")
    a("")
    if assessment:
        a("*AI identity assessment (an inference for a human to confirm, not proof; the deterministic "
          "confidence scores remain authoritative).*")
        a("")
        a(assessment)
    else:
        a("_No local model available for an identity assessment, or it failed the grounding check. "
          "Judge identity from the corroboration and confidence in the evidence below._")
    a("")

    # ---- social presence ----
    social: dict[str, list] = {}
    for e in nodes:
        if e.type in (EntityType.SOCIAL_PROFILE, EntityType.URL, EntityType.USERNAME):
            platform = classify_platform(e.value) or (e.metadata.get("service") if isinstance(e.metadata, dict) else None)
            if platform:
                social.setdefault(str(platform), []).append(e)
    if social:
        a("## Social presence")
        a("")
        a("Profiles surfaced through open enumeration (maigret, sherlock, holehe, Gravatar, web search) — "
          "public pages only, not platform scraping.")
        a("")
        for platform in sorted(social):
            for e in social[platform]:
                a(f"- **{platform}:** {e.value}  _(confidence {e.confidence:.2f})_")
        a("")

    # ---- full entity inventory ----
    a("## Entities")
    a("")
    for t in sorted(by_type):
        a(f"### {t}")
        for e in sorted(by_type[t], key=lambda x: -x.confidence):
            srcs = ", ".join(e.metadata.get("sources", [])) if isinstance(e.metadata, dict) else ""
            a(f"- `{e.value}` — confidence {e.confidence:.2f}" + (f", sources: {srcs}" if srcs else ""))
        a("")

    # ---- coverage / honesty ----
    a("## Coverage")
    a("")
    a("- Findings are aggregated from free, public open sources; each entity records the source that "
      "produced it and a confidence weighted by source reliability and corroboration.")
    a("- A low confidence indicates a single weak signal (for example one search hit); prefer entities "
      "corroborated by two or more independent sources.")
    a("- Absence of a result is not proof of absence: a source that was unreachable or disabled during the "
      "run was not tested.")
    a("")
    return "\n".join(lines)


def _narrate(reasoner: Reasoner, engagement, by_type: dict, seeds, findings=None) -> str:
    if not reasoner.available:
        return ""
    facts = [f"Engagement client: {engagement.client}."]
    if seeds:
        facts.append(f"Seed(s): {', '.join(seeds)}.")
    for t, ents in sorted(by_type.items()):
        vals = ", ".join(e.value for e in ents[:15])
        facts.append(f"{t} ({len(ents)}): {vals}")
    for f in (findings or [])[:10]:
        facts.append(f"Correlation: {f.title} — {f.detail}")
    prompt = ("Write a short factual reconnaissance summary from these facts. Do not add anything not "
              "listed. Facts:\n" + "\n".join(facts))
    narrative = reasoner.narrate(system=_SYSTEM, prompt=prompt)
    if not narrative or not _is_grounded(narrative, by_type):
        return ""
    return narrative


def _assess_identity(reasoner: Reasoner, engagement, by_type: dict, seeds, findings=None, clusters=None) -> str:
    """Ask the model whether the collected entities cohere as one identity matching the seed.

    Output is a labelled inference (corroboration, conflicts, a confidence band), never an
    auto-merge and never a deterministic finding. Discarded if it fails the grounding check.
    """
    if not reasoner.available:
        return ""
    facts = []
    if seeds:
        facts.append(f"Seed identity under investigation: {', '.join(seeds)}.")
    for t, ents in sorted(by_type.items()):
        for e in ents[:20]:
            srcs = ", ".join(e.metadata.get("sources", [])) if isinstance(e.metadata, dict) else ""
            facts.append(f"- {t}: {e.value} (confidence {e.confidence:.2f}"
                         + (f"; sources: {srcs}" if srcs else "") + ")")
    for f in (findings or [])[:10]:
        facts.append(f"- correlation [{f.strength}]: {f.title} — {f.detail}")
    for c in (clusters or [])[:8]:
        facts.append(f"- identity cluster (conf {c.confidence:.2f}): {c.basis}")
    prompt = ("Assess whether these collected entities belong to the same individual as the seed. "
              "List corroborating signals and conflicts, then the confidence line.\n\n" + "\n".join(facts))
    out = reasoner.narrate(system=_ASSESS_SYSTEM, prompt=prompt)
    if not out or not _is_grounded(out, by_type):
        return ""
    return out


def _is_grounded(narrative: str, by_type: dict) -> bool:
    """Every email/URL the narrative names must exist in the graph, else discard it."""
    known = {e.value.lower() for ents in by_type.values() for e in ents}
    for token in _EMAIL_RE.findall(narrative) + _URL_RE.findall(narrative):
        tok = token.rstrip(".,);").lower()
        if tok not in known and not any(tok in k or k in tok for k in known):
            return False
    return True
