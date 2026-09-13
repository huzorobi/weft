"""Graph analytics over the entity graph — pure Python, no plugin required.

Betweenness centrality ranks the nodes that bridge the graph — the gatekeepers a real
analyst looks at first, the entity that links two otherwise-separate clusters. Community
detection (connected components) groups the graph into its natural clusters. Both run on
the in-memory graph, so no Neo4j GDS plugin is needed; the graphs Weft builds are small
enough that exact algorithms are fine.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from weft.core.graphstore import InMemoryGraph


@dataclass
class Analytics:
    pivots: list[tuple[str, float]] = field(default_factory=list)   # (entity key, betweenness), ranked
    communities: list[list[str]] = field(default_factory=list)       # lists of entity keys


def _adjacency(graph: InMemoryGraph) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {k: set() for k in graph.nodes}
    for e in graph.edges:
        if e.src_key in adj and e.dst_key in adj and e.src_key != e.dst_key:
            adj[e.src_key].add(e.dst_key)
            adj[e.dst_key].add(e.src_key)
    return adj


def betweenness_centrality(adj: dict[str, set[str]]) -> dict[str, float]:
    """Brandes' algorithm for unweighted, undirected graphs."""
    cb = {v: 0.0 for v in adj}
    for s in adj:
        stack: list[str] = []
        pred: dict[str, list[str]] = {w: [] for w in adj}
        sigma = {w: 0.0 for w in adj}
        sigma[s] = 1.0
        dist = {w: -1 for w in adj}
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {w: 0.0 for w in adj}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]
    for v in cb:      # undirected: each pair counted twice
        cb[v] /= 2.0
    return cb


def communities(adj: dict[str, set[str]]) -> list[list[str]]:
    """Connected components via union-find."""
    parent = {v: v for v in adj}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for v in adj:
        for w in adj[v]:
            parent[find(v)] = find(w)
    groups: dict[str, list[str]] = {}
    for v in adj:
        groups.setdefault(find(v), []).append(v)
    return sorted(groups.values(), key=len, reverse=True)


def graph_analytics(graph: InMemoryGraph, *, top: int = 8) -> Analytics:
    adj = _adjacency(graph)
    if not adj:
        return Analytics()
    cb = betweenness_centrality(adj)
    pivots = sorted(cb.items(), key=lambda kv: kv[1], reverse=True)
    pivots = [(k, round(v, 3)) for k, v in pivots if v > 0][:top]
    return Analytics(pivots=pivots, communities=communities(adj))
