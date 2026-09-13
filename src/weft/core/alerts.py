"""High-value pivot alerting.

Turns the analysis passes into a short, ranked triage list: the events an analyst should look
at first. It escalates the risk findings (sanctions, known-exploited CVEs, malicious infra),
flags high-confidence identity clusters (a subject's accounts converging), and surfaces the top
graph pivot (the node that bridges the graph). Pure and deterministic — it only reads what the
correlation, resolution, and analytics passes already produced.
"""
from __future__ import annotations

from dataclasses import dataclass

_LEVEL_ORDER = {"critical": 0, "high": 1, "notable": 2}
_RISK_LEVEL = {"sanctions_match": ("critical", "Sanctions match"),
               "known_exploited_cve": ("critical", "Known-exploited vulnerability"),
               "malicious_infrastructure": ("high", "Malicious infrastructure")}


@dataclass(frozen=True)
class Alert:
    level: str     # critical | high | notable
    title: str
    detail: str


def raise_alerts(findings, resolution, analytics, *, graph=None,
                 cluster_confidence: float = 0.85, cluster_size: int = 3) -> list[Alert]:
    out: list[Alert] = []
    for f in findings:
        if f.rule in _RISK_LEVEL:
            level, _label = _RISK_LEVEL[f.rule]   # the finding title already leads with the label
            out.append(Alert(level, f.title, f.detail))
    for c in getattr(resolution, "clusters", []):
        if c.confidence >= cluster_confidence and c.size >= cluster_size:
            out.append(Alert("high", f"High-confidence identity cluster: {c.label}",
                             f"{c.size} entities converge — {c.basis}."))
    pivots = getattr(analytics, "pivots", []) or []
    if pivots:
        key, score = pivots[0]
        label = key
        if graph is not None and key in getattr(graph, "nodes", {}):
            n = graph.nodes[key]
            label = f"{n.type.value} '{n.value}'"
        out.append(Alert("notable", f"Key pivot: {label}",
                         f"Highest-betweenness node (score {score}); the best entity to pursue next."))
    return sorted(out, key=lambda a: _LEVEL_ORDER.get(a.level, 3))
