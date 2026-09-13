"""Admiralty (NATO) source grading for entities.

The Admiralty code rates a piece of information on two axes: source reliability (A completely
reliable … F cannot be judged) and information credibility (1 confirmed … 6 cannot be judged).
Weft grades each entity from its reliability-weighted confidence and how many independent
sources corroborate it, giving analysts the familiar two-character code (e.g. "B2"). Pure.
"""
from __future__ import annotations

from dataclasses import dataclass

from weft.core.entity import Entity


@dataclass(frozen=True)
class Admiralty:
    reliability: str   # A-F
    credibility: int   # 1-6

    @property
    def code(self) -> str:
        return f"{self.reliability}{self.credibility}"


def reliability_letter(confidence: float) -> str:
    if confidence >= 0.9:
        return "A"   # completely reliable
    if confidence >= 0.75:
        return "B"   # usually reliable
    if confidence >= 0.6:
        return "C"   # fairly reliable
    if confidence >= 0.4:
        return "D"   # not usually reliable
    if confidence > 0.0:
        return "E"   # unreliable
    return "F"       # cannot be judged


def credibility_digit(source_count: int, confidence: float) -> int:
    if source_count >= 3:
        return 1     # confirmed by other sources
    if source_count == 2:
        return 2     # probably true
    if confidence >= 0.7:
        return 3     # possibly true
    if confidence >= 0.4:
        return 4     # doubtful
    return 5         # improbable (a single weak signal)


def source_count(entity: Entity) -> int:
    md = entity.metadata if isinstance(entity.metadata, dict) else {}
    srcs = md.get("sources") or [entity.source_module]
    return len({s for s in srcs if s})


def grade_entity(entity: Entity) -> Admiralty:
    return Admiralty(reliability_letter(entity.confidence),
                     credibility_digit(source_count(entity), entity.confidence))
