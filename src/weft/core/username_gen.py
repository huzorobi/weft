"""Generate candidate usernames from a person's name.

A name is turned into the handles a person is likely to have used: firstlast, first.last,
flast, first_last, and so on. These are *candidates*, not confirmations — a match on a
common permutation may be a different person entirely — so the caller must treat hits as
low-confidence leads. Deterministic and bounded.
"""
from __future__ import annotations

import re


def candidates_from_name(name: str, *, cap: int = 8) -> list[str]:
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", (name or "").lower()) if t]
    if not tokens:
        return []
    if len(tokens) == 1:
        return [tokens[0]][:cap]

    first, last = tokens[0], tokens[-1]      # ignore middle names for handle-building
    fi, li = first[0], last[0]
    ordered = [
        f"{first}{last}",
        f"{first}.{last}",
        f"{first}_{last}",
        f"{fi}{last}",
        f"{first}{li}",
        f"{last}{first}",
        f"{last}.{first}",
        f"{first}",
        f"{last}",
        f"{fi}{li}{last}",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for c in ordered:
        if c and c not in seen and len(c) >= 3:
            seen.add(c)
            out.append(c)
        if len(out) >= cap:
            break
    return out
