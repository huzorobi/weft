"""Deterministic correlation engine.

Collection produces entities; this pass finds the *patterns* across them — the same
handle on several platforms, a name corroborated by independent sources, a person tied to
companies, IPs clustered in one place, a hub node that bridges the graph. Each pattern
becomes a :class:`Finding` with an explicit confidence and provenance (which sources and
which rule produced it).

The findings are deterministic and repeatable. The local model reasons *about* them; it
never invents them. This is the evidence layer beneath the narrative and the identity
assessment.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.reporting.platforms import classify_platform


@dataclass(frozen=True)
class Finding:
    rule: str
    title: str
    detail: str
    confidence: float                 # 0..1
    entity_keys: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()     # provenance: the modules behind the evidence

    @property
    def strength(self) -> str:
        return "strong" if self.confidence >= 0.75 else "notable" if self.confidence >= 0.5 else "weak"


def _sources_of(entities: list[Entity]) -> tuple[str, ...]:
    s: set[str] = set()
    for e in entities:
        md = e.metadata if isinstance(e.metadata, dict) else {}
        s.update(md.get("sources", [e.source_module]))
    return tuple(sorted(s))


def _avg_conf(entities: list[Entity]) -> float:
    return round(sum(e.confidence for e in entities) / len(entities), 3) if entities else 0.0


class CorrelationEngine:
    """Runs every rule over the graph and returns findings, strongest first."""

    def run(self, graph: InMemoryGraph) -> list[Finding]:
        findings: list[Finding] = []
        for rule in (_multi_platform, _corroborated_names, _person_orgs, _email_accounts,
                     _shared_registrant, _geo_cluster, _hub_nodes, _multi_source_anchor,
                     _sanctions_hits, _exploited_cves, _malicious_infra, _shared_key_identity):
            try:
                findings.extend(rule(graph))
            except Exception:  # a bad rule never breaks the pass
                continue
        return sorted(findings, key=lambda f: f.confidence, reverse=True)


# --- rules ------------------------------------------------------------------

def _multi_platform(graph: InMemoryGraph) -> list[Finding]:
    profiles = [e for e in graph.nodes.values()
                if e.type in (EntityType.SOCIAL_PROFILE, EntityType.URL, EntityType.USERNAME)]
    by_platform: dict[str, list[Entity]] = defaultdict(list)
    for e in profiles:
        p = classify_platform(e.value) or (e.metadata.get("service") if isinstance(e.metadata, dict) else None)
        if p:
            by_platform[str(p)].append(e)
    if len(by_platform) < 2:
        return []
    involved = [e for lst in by_platform.values() for e in lst]
    return [Finding(
        rule="multi_platform_presence",
        title=f"Presence across {len(by_platform)} platforms",
        detail="Profiles found on: " + ", ".join(sorted(by_platform)),
        confidence=min(1.0, 0.4 + 0.1 * len(by_platform)),
        entity_keys=tuple(e.key() for e in involved),
        sources=_sources_of(involved),
    )]


def _corroborated_names(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        if e.type is not EntityType.NAME:
            continue
        srcs = _sources_of([e])
        if len(srcs) >= 2:
            out.append(Finding(
                rule="corroborated_name",
                title=f"Name corroborated by {len(srcs)} sources",
                detail=f'"{e.value}" reported independently by {", ".join(srcs)}.',
                confidence=min(1.0, 0.6 + 0.15 * (len(srcs) - 1)),
                entity_keys=(e.key(),), sources=srcs))
    return out


def _linked(graph: InMemoryGraph, key: str) -> list[str]:
    return [ed.dst_key for ed in graph.edges if ed.src_key == key] + \
           [ed.src_key for ed in graph.edges if ed.dst_key == key]


def _person_orgs(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        if e.type not in (EntityType.PERSON, EntityType.NAME):
            continue
        orgs = [graph.nodes[k] for k in _linked(graph, e.key())
                if k in graph.nodes and graph.nodes[k].type is EntityType.ORGANISATION]
        if orgs:
            out.append(Finding(
                rule="person_organisation_link",
                title=f"{e.value} linked to {len(orgs)} organisation(s)",
                detail="Organisations: " + ", ".join(o.value for o in orgs),
                confidence=_avg_conf([e] + orgs),
                entity_keys=tuple([e.key()] + [o.key() for o in orgs]),
                sources=_sources_of([e] + orgs)))
    return out


def _email_accounts(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        if e.type is not EntityType.EMAIL:
            continue
        accts = [graph.nodes[k] for k in _linked(graph, e.key())
                 if k in graph.nodes and graph.nodes[k].type in
                 (EntityType.SOCIAL_PROFILE, EntityType.USERNAME, EntityType.URL)]
        if len(accts) >= 2:
            out.append(Finding(
                rule="email_to_accounts",
                title=f"Email tied to {len(accts)} accounts",
                detail=f"{e.value} links to " + ", ".join(a.value[:40] for a in accts),
                confidence=min(1.0, 0.5 + 0.1 * len(accts)),
                entity_keys=tuple([e.key()] + [a.key() for a in accts]),
                sources=_sources_of([e] + accts)))
    return out


def _shared_registrant(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        if e.type is not EntityType.ORGANISATION:
            continue
        domains = [graph.nodes[k] for k in _linked(graph, e.key())
                   if k in graph.nodes and graph.nodes[k].type is EntityType.DOMAIN]
        if len(domains) >= 2:
            out.append(Finding(
                rule="shared_registrant",
                title=f"{e.value} linked to {len(domains)} domains",
                detail="Domains: " + ", ".join(d.value for d in domains),
                confidence=_avg_conf([e] + domains),
                entity_keys=tuple([e.key()] + [d.key() for d in domains]),
                sources=_sources_of([e] + domains)))
    return out


def _geo_cluster(graph: InMemoryGraph) -> list[Finding]:
    by_country: dict[str, list[Entity]] = defaultdict(list)
    for e in graph.nodes.values():
        if e.type is EntityType.IP and isinstance(e.metadata, dict) and e.metadata.get("country"):
            by_country[e.metadata["country"]].append(e)
    out = []
    for country, ips in by_country.items():
        if len(ips) >= 2:
            out.append(Finding(
                rule="geo_cluster",
                title=f"{len(ips)} IPs in {country}",
                detail="IPs: " + ", ".join(i.value for i in ips[:8]),
                confidence=min(1.0, 0.4 + 0.08 * len(ips)),
                entity_keys=tuple(i.key() for i in ips), sources=_sources_of(ips)))
    return out


def _hub_nodes(graph: InMemoryGraph, *, threshold: int = 4) -> list[Finding]:
    degree: dict[str, int] = defaultdict(int)
    for ed in graph.edges:
        degree[ed.src_key] += 1
        degree[ed.dst_key] += 1
    out = []
    for key, deg in degree.items():
        if deg >= threshold and key in graph.nodes:
            e = graph.nodes[key]
            out.append(Finding(
                rule="hub_node",
                title=f"Hub: {e.type.value} '{e.value[:40]}' ({deg} links)",
                detail="A highly-connected node; a strong pivot point in the graph.",
                confidence=min(1.0, 0.5 + 0.05 * deg),
                entity_keys=(key,), sources=_sources_of([e])))
    return out


def _multi_source_anchor(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        srcs = _sources_of([e])
        if len(srcs) >= 3:
            out.append(Finding(
                rule="multi_source_anchor",
                title=f"High-confidence anchor: {e.type.value} '{e.value[:40]}'",
                detail=f"Confirmed by {len(srcs)} independent sources: {', '.join(srcs)}.",
                confidence=min(1.0, 0.7 + 0.1 * (len(srcs) - 2)),
                entity_keys=(e.key(),), sources=srcs))
    return out


# --- risk & identity rules (surface the enrichment signals) -----------------

def _meta(e: Entity) -> dict:
    return e.metadata if isinstance(e.metadata, dict) else {}


def _sanctions_hits(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        md = _meta(e)
        if md.get("sanctioned"):
            lst, prog = md.get("list"), md.get("programme")
            out.append(Finding(
                rule="sanctions_match",
                title=f"Sanctions match: {e.value[:50]}",
                detail=(f"Potential match on {lst or 'a sanctions list'}"
                        + (f" (programme {prog})" if prog else "") + " — confirm identity before acting."),
                confidence=e.confidence,
                entity_keys=(e.key(),), sources=_sources_of([e])))
    return out


def _exploited_cves(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        md = _meta(e)
        if e.type is EntityType.CVE and md.get("known_exploited"):
            ransomware = str(md.get("ransomware_use", "")).lower() == "known"
            out.append(Finding(
                rule="known_exploited_cve",
                title=f"Known-exploited vulnerability: {e.value}",
                detail=((md.get("kev_name") or "Listed in CISA KEV — actively exploited in the wild.")
                        + (" Known ransomware use." if ransomware else "")),
                confidence=max(e.confidence, 0.9),
                entity_keys=(e.key(),), sources=_sources_of([e])))
    return out


def _malicious_infra(graph: InMemoryGraph) -> list[Finding]:
    labels = {"malware_ioc": "a malware/C2 indicator (abuse.ch)",
              "listed": "threat blocklists",
              "flagged": "malware-filtering DNS"}
    out = []
    for e in graph.nodes.values():
        md = _meta(e)
        rep = md.get("reputation")
        if rep in labels:
            extra = (md.get("malware")
                     or (f"{md.get('list_count')} lists" if md.get("list_count") else "")
                     or (", ".join(md.get("blocked_by", [])) if md.get("blocked_by") else ""))
            out.append(Finding(
                rule="malicious_infrastructure",
                title=f"Malicious infrastructure: {e.type.value} {e.value[:40]}",
                detail=f"Flagged by {labels[rep]}" + (f": {extra}" if extra else "") + ".",
                confidence=e.confidence,
                entity_keys=(e.key(),), sources=_sources_of([e])))
    return out


def _shared_key_identity(graph: InMemoryGraph) -> list[Finding]:
    out = []
    for e in graph.nodes.values():
        md = _meta(e)
        if "PGP key" in str(md.get("linked_via", "")):
            other = md.get("with_email") or md.get("for_email")
            out.append(Finding(
                rule="shared_pgp_key",
                title=f"Identity link via shared PGP key: {e.value[:50]}",
                detail=(f"{e.value} shares a PGP key with {other} — a strong identity link."
                        if other else f"{e.value} is bound to a subject's PGP key."),
                confidence=max(e.confidence, 0.8),
                entity_keys=(e.key(),), sources=_sources_of([e])))
    return out
