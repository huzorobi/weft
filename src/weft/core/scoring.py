"""Confidence scoring and entity merging.

A common name throws dozens of false matches, so confidence is what keeps the graph
usable. The v1 model is deliberately simple and honest, tuned later (Phase 6):

  * Each module declares a source-reliability weight in ``[0,1]``.
  * A finding's confidence starts at that weight.
  * When the same entity (same dedup key) is produced by more than one independent
    source, corroboration raises confidence toward 1.0 with diminishing returns.

The rule "two independent sources beat one fuzzy hit" falls straight out of this.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from weft.core.entity import Entity


def base_confidence(reliability: float) -> float:
    return max(0.0, min(1.0, reliability))


def corroborated(confidence: float, corroborations: int) -> float:
    """Raise ``confidence`` for each independent corroboration beyond the first.

    One source -> unchanged. Each extra source closes ~40% of the remaining gap to
    1.0, so noise never reaches certainty on volume alone but genuine multi-source
    agreement climbs quickly.
    """
    conf = confidence
    for _ in range(max(0, corroborations - 1)):
        conf = conf + 0.4 * (1.0 - conf)
    return min(1.0, conf)


@dataclass
class MergedEntity:
    """An entity node as accumulated across sources."""

    entity: Entity
    sources: set[str] = field(default_factory=set)

    @property
    def confidence(self) -> float:
        # corroboration counts distinct sources
        return corroborated(self.entity.confidence, len(self.sources))


def merge(existing: Entity, incoming: Entity) -> Entity:
    """Merge two findings for the same key: union metadata, keep the higher base
    confidence, remember both source tags in metadata['sources']."""
    if existing.key() != incoming.key():
        raise ValueError("cannot merge entities with different keys")
    md = dict(existing.metadata)
    for k, v in incoming.metadata.items():
        md.setdefault(k, v)
    sources = set(md.get("sources", []))
    sources.update(existing.metadata.get("sources", [existing.source_module]))
    sources.update(incoming.metadata.get("sources", [incoming.source_module]))
    md["sources"] = sorted(sources)
    base = max(existing.confidence, incoming.confidence)
    return Entity(
        type=existing.type,
        value=existing.value,
        source_module=existing.source_module,
        confidence=corroborated(base, len(sources)),
        seed_id=existing.seed_id,
        metadata=md,
        label=existing.label or incoming.label,
    )
