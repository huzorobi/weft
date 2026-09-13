"""Sanctions screening against OFAC (US) and the UN consolidated list (free, keyless).

Screens a name / person / organisation against two authoritative, public-domain sanctions
lists and returns any potential matches with the sanctioning programme and reference. Both
lists are bulk files, so this module downloads and parses each once per run and caches it;
matching then runs locally. Passive (reads a published list, never contacts the subject).

A name match on a screening list is a *lead to confirm*, not a verdict — matches carry
moderate confidence and are labelled as potential, in line with sanctions-screening practice
(the false-positive rate on common names is high, so a human confirms identity).

The trade.gov Consolidated Screening List (one query, OFAC+EU+UN+UK+more) is the natural
upgrade but needs a free api.data.gov key; when that key is present a future module can
supersede these two bulk lists.
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
UN_CONSOLIDATED_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[.,;:'\"()\-/]")
# Name particles, honorifics and company suffixes carry no identifying signal — dropping them
# stops "de"/"al"/"ltd" from bridging unrelated names.
_STOP = {
    "de", "of", "the", "and", "al", "el", "la", "le", "van", "von", "der", "den", "del",
    "da", "di", "bin", "ibn", "abu", "abd", "ben", "san", "santa", "st",
    "ltd", "limited", "sa", "co", "company", "group", "inc", "corp", "corporation",
    "llc", "plc", "gmbh", "holdings", "holding", "trading", "international",
}
_MIN_QUERY_LEN = 4  # below this a name match is meaningless noise


@dataclass
class SanctionRecord:
    name: str
    kind: EntityType             # PERSON or ORGANISATION
    source: str                  # "OFAC SDN" | "UN Consolidated"
    programme: str | None = None
    reference: str | None = None
    remarks: str | None = None
    aliases: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def parse_ofac_csv(text: str) -> list[SanctionRecord]:
    """OFAC SDN CSV: ent_num, name, sdn_type, programme, title, <vessel cols>, remarks."""
    out: list[SanctionRecord] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4:
            continue
        name = (row[1] or "").strip()
        if not name or name == "-0-":
            continue
        sdn_type = (row[2] or "").strip().strip('"')
        kind = EntityType.PERSON if sdn_type.lower() == "individual" else EntityType.ORGANISATION
        prog = _clean(row[3])
        remarks = _clean(row[-1]) if len(row) > 4 else None
        aliases = _ofac_aliases(remarks)
        out.append(SanctionRecord(name=name, kind=kind, source="OFAC SDN",
                                  programme=prog, reference=(row[0] or "").strip(),
                                  remarks=remarks, aliases=aliases))
    return out


def _clean(v: str | None) -> str | None:
    v = (v or "").strip().strip('"').strip()
    return None if not v or v == "-0-" else v


def _ofac_aliases(remarks: str | None) -> list[str]:
    if not remarks:
        return []
    # OFAC packs aliases into remarks as "a.k.a. 'NAME'."
    return [m.strip() for m in re.findall(r"a\.k\.a\.\s+'([^']+)'", remarks)]


def parse_un_xml(text: str) -> list[SanctionRecord]:
    out: list[SanctionRecord] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for indiv in root.iter("INDIVIDUAL"):
        name = _join_names(indiv)
        if name:
            out.append(SanctionRecord(
                name=name, kind=EntityType.PERSON, source="UN Consolidated",
                programme=_text(indiv, "UN_LIST_TYPE"), reference=_text(indiv, "REFERENCE_NUMBER"),
                remarks=_text(indiv, "COMMENTS1"), aliases=_un_aliases(indiv, "INDIVIDUAL_ALIAS")))
    for ent in root.iter("ENTITY"):
        name = _text(ent, "FIRST_NAME")
        if name:
            out.append(SanctionRecord(
                name=name.strip(), kind=EntityType.ORGANISATION, source="UN Consolidated",
                programme=_text(ent, "UN_LIST_TYPE"), reference=_text(ent, "REFERENCE_NUMBER"),
                remarks=_text(ent, "COMMENTS1"), aliases=_un_aliases(ent, "ENTITY_ALIAS")))
    return out


def _text(node, tag) -> str | None:
    el = node.find(tag)
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


def _join_names(indiv) -> str:
    parts = [_text(indiv, t) for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
    return " ".join(p for p in parts if p).strip()


def _un_aliases(node, alias_tag) -> list[str]:
    out = []
    for alias in node.findall(alias_tag):
        val = alias.find("ALIAS_NAME")
        if val is not None and val.text and val.text.strip():
            out.append(val.text.strip())
    return out


def _sig_tokens(s: str) -> set[str]:
    """Significant name tokens: normalised, punctuation-stripped, particles/suffixes removed."""
    words = _PUNCT.sub(" ", _norm(s)).split()
    return {w for w in words if len(w) >= 2 and w not in _STOP}


def match_records(query: str, records: list[SanctionRecord]) -> list[SanctionRecord]:
    """Return records whose name or an alias matches the query on significant name tokens.

    A match requires one token set to fully contain the other (so a shorter listing name still
    matches a fuller query, and vice versa) AND either two shared tokens or one shared token of
    length >= 5. Bare substring matching is deliberately not used: it lets short fragments such
    as "cuba" bridge unrelated entities, which floods sanctions screening with false positives.
    """
    if len(_norm(query)) < _MIN_QUERY_LEN:
        return []
    qt = _sig_tokens(query)
    if not qt:
        return []
    hits: list[SanctionRecord] = []
    for r in records:
        if any(_token_match(qt, _sig_tokens(c)) for c in (r.name, *r.aliases) if c):
            hits.append(r)
    return hits


def _token_match(qt: set[str], ct: set[str]) -> bool:
    # One name must refine the other (subset), so "John Smith" flags every John Smith but
    # "John Smith Cuba" does not match "John Smith Argentina".
    if not ct or not (qt <= ct or ct <= qt):
        return False
    inter = qt & ct  # == the smaller set, given containment
    if len(inter) >= 2:
        return True
    # a single shared token only counts when one side is genuinely a one-word name, and the
    # word is distinctive (>= 5 chars) — this stops a common word like "banco" bridging banks.
    return len(inter) == 1 and len(next(iter(inter))) >= 5


@register
class SanctionsScreen(Module):
    name = "sanctions_screen"
    accepts = [EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION]
    produces = [EntityType.PERSON, EntityType.ORGANISATION]
    access = Access.FREE_API
    reliability = 0.5   # a name match on a screening list is a lead to confirm, not a verdict
    timeout_s = 60

    def __init__(self) -> None:
        self._records: list[SanctionRecord] | None = None
        self._lock: asyncio.Lock | None = None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def _load(self, ctx) -> list[SanctionRecord]:
        if self._records is not None:
            return self._records
        if self._lock is None:
            self._lock = asyncio.Lock()   # lazy so it binds to the running loop
        async with self._lock:
            if self._records is not None:
                return self._records
            records: list[SanctionRecord] = []
            s, ofac = await ctx.http.get_text(OFAC_SDN_CSV)
            if s == 200 and ofac:
                records += parse_ofac_csv(ofac)
            s, un = await ctx.http.get_text(UN_CONSOLIDATED_XML)
            if s == 200 and un:
                records += parse_un_xml(un)
            self._records = records
            return records

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        records = await self._load(ctx)
        out: list[Entity] = []
        for r in match_records(entity.value, records):
            out.append(Entity.make(
                r.kind, r.name, source_module=self.name, confidence=self.reliability,
                seed_id=entity.seed_id,
                metadata={
                    "sanctioned": True,
                    "match": "potential",   # confirm identity before acting
                    "list": r.source,
                    "programme": r.programme,
                    "reference": r.reference,
                    "aliases": r.aliases or None,
                    "remarks": (r.remarks[:300] if r.remarks else None),
                    "matched_seed": entity.value,
                },
                label=f"sanctioned ({r.source})"))
        return out
