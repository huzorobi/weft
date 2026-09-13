"""Entity resolution — cluster the entities that are the same identity.

Exact-key dedup collapses "email:x" seen twice, but it cannot tell that a GitHub handle,
a Reddit handle, and an email local-part are one person, nor split two people who share a
common name. This pass clusters person-identifying entities on shared signals — a shared PGP key (a cryptographic
link), the same handle across platforms, a handle that contains a name's tokens, an email
local-part that matches a handle — and records weaker leads as "possibly the same".

It never hard-merges nodes; it produces clusters and SAME_AS / POSSIBLY_SAME_AS links with
scores, so a coincidental match stays visible and reversible. Deterministic and explainable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph

_IDENTITY_TYPES = (EntityType.USERNAME, EntityType.SOCIAL_PROFILE, EntityType.EMAIL,
                   EntityType.NAME, EntityType.PERSON)

# Path words that show up as "handles" when parsing profile URLs but are not identities
# (e.g. .../forum/members/, .../user/, .../index) — never cluster on these.
_JUNK_HANDLES = frozenset({
    "members", "member", "user", "users", "profile", "profiles", "index", "home", "about",
    "search", "login", "logout", "signin", "signup", "admin", "settings", "account", "accounts",
    "page", "pages", "view", "forum", "forums", "topic", "thread", "threads", "post", "posts",
    "id", "u", "p", "en", "www", "me", "public", "default", "unknown", "null", "none",
})


@dataclass(frozen=True)
class IdentityCluster:
    label: str
    keys: tuple[str, ...]
    confidence: float
    basis: str

    @property
    def size(self) -> int:
        return len(self.keys)


@dataclass
class Resolution:
    clusters: list[IdentityCluster] = field(default_factory=list)
    possibly_same: list[tuple[str, str, float, str]] = field(default_factory=list)  # (a, b, score, why)


def handle_of(entity: Entity) -> str | None:
    """Extract a comparable handle from a username / social profile / email."""
    if entity.type is EntityType.USERNAME:
        return entity.value.lower().lstrip("@") or None
    if entity.type is EntityType.EMAIL:
        return entity.value.split("@", 1)[0].lower() or None
    if entity.type is EntityType.SOCIAL_PROFILE:
        seg = [s for s in urlsplit(entity.value).path.split("/") if s]
        if seg:
            return seg[-1].lower().lstrip("@") or None
    return None


def _name_tokens(value: str) -> list[str]:
    import re
    return [t for t in re.split(r"[^a-z0-9]+", value.lower()) if len(t) >= 2]


def resolve_identities(graph: InMemoryGraph, *, name_sim: float = 0.86) -> Resolution:
    res = Resolution()
    nodes = [e for e in graph.nodes.values() if e.type in _IDENTITY_TYPES]

    # 1) cluster entities that share a handle (across platforms / sources)
    by_handle: dict[str, list[Entity]] = {}
    for e in nodes:
        h = handle_of(e)
        if h:
            by_handle.setdefault(h, []).append(e)

    names = [e for e in nodes if e.type in (EntityType.NAME, EntityType.PERSON)]
    used_names: set[str] = set()

    for handle, members in by_handle.items():
        if len(members) < 2 or len(handle) < 3 or handle in _JUNK_HANDLES:
            continue
        keys = [m.key() for m in members]
        # Confidence rests on how many INDEPENDENT sources corroborate the handle, not on how
        # many accounts share it. One module checking a guessed handle across 20 sites is weak;
        # several independent modules agreeing on a handle is strong.
        n_sources = len({m.source_module for m in members if m.source_module})
        matched_name = None
        for n in names:
            toks = _name_tokens(n.value)
            if toks and all(t in handle for t in toks):
                keys.append(n.key())
                used_names.add(n.key())
                matched_name = n.value
        conf = min(0.95, 0.4 + 0.15 * n_sources)
        if matched_name:
            conf = min(0.97, conf + 0.1)   # a matching real name is corroboration
        basis = (f"shared handle '{handle}' — corroborated by {n_sources} independent source(s) "
                 f"across {len(members)} account(s)"
                 + (f"; matches name '{matched_name}'" if matched_name else ""))
        res.clusters.append(IdentityCluster(label=handle, keys=tuple(dict.fromkeys(keys)),
                                             confidence=round(conf, 2), basis=basis))

    # 1.5) strong cryptographic links: entities bound by a shared PGP key are the same person
    #      with far higher certainty than a handle heuristic (a key proves control of its uids).
    by_key_anchor: dict[str, set[str]] = {}
    for e in graph.nodes.values():
        md = e.metadata if isinstance(e.metadata, dict) else {}
        if "PGP key" in str(md.get("linked_via", "")):
            anchor = md.get("with_email") or md.get("for_email")
            if anchor:
                grp = by_key_anchor.setdefault(str(anchor).lower(), set())
                grp.add(e.key())
                anchor_key = f"email:{str(anchor).lower()}"
                if anchor_key in graph.nodes:
                    grp.add(anchor_key)
    for anchor, keys in by_key_anchor.items():
        if len(keys) >= 2:
            res.clusters.append(IdentityCluster(
                label=f"pgp:{anchor}", keys=tuple(sorted(keys)), confidence=0.9,
                basis=f"shared PGP key with {anchor} (cryptographic link)"))

    # 2) weak leads: fuzzy-similar names that were not already tied to a handle cluster
    free = [n for n in names if n.key() not in used_names]
    for i in range(len(free)):
        for j in range(i + 1, len(free)):
            a, b = free[i], free[j]
            if a.value.lower() == b.value.lower():
                continue
            ratio = SequenceMatcher(None, a.value.lower(), b.value.lower()).ratio()
            if ratio >= name_sim:
                res.possibly_same.append((a.key(), b.key(), round(ratio, 2),
                                          f"similar names '{a.value}' / '{b.value}'"))

    res.clusters.sort(key=lambda c: (c.confidence, c.size), reverse=True)
    return res
