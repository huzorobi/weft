"""Build a chronology from the temporal signals already in the graph.

WHOIS registration and expiry dates, Wayback and Common Crawl capture timestamps — these
are scattered across entity metadata. This pass pulls them into one ordered timeline, so a
reader can see when a domain was registered, when it first appeared in an archive, and how
the footprint developed over time. Deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from weft.core.entity import EntityType
from weft.core.graphstore import InMemoryGraph


@dataclass(frozen=True)
class TimelineEntry:
    date: str            # YYYY-MM-DD
    event: str
    entity_key: str


def _norm_date(v) -> str | None:
    s = str(v)
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)      # 20260807... (wayback / common crawl)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)     # ISO
    if m:
        return m.group(0)
    return None


def build_timeline(graph: InMemoryGraph) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    seen: set[tuple[str, str]] = set()

    def add(date, event, key):
        d = _norm_date(date)
        if d and (d, event) not in seen:
            seen.add((d, event))
            entries.append(TimelineEntry(d, event, key))

    for key, e in graph.nodes.items():
        md = e.metadata if isinstance(e.metadata, dict) else {}
        events = md.get("registration_events")
        if isinstance(events, dict):
            for action, date in events.items():
                add(date, f"{action} of {e.value}", key)
        if md.get("first_snapshot"):
            add(md["first_snapshot"], f"first archived: {e.value[:50]}", key)
        if md.get("timestamp") and md.get("discovered_via", "").startswith("Common Crawl"):
            add(md["timestamp"], f"crawled: {e.value[:50]}", key)

    entries.sort(key=lambda x: x.date)
    return entries
