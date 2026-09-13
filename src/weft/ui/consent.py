"""One-time terms & conditions acceptance for Weft.

The operator accepts the terms once, at first launch; the acceptance (operator, version,
timestamp) is persisted so it is not asked again unless the terms change. This is the launch
responsibility gate — the run-time scope gate still applies underneath.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

TERMS_VERSION = "2026-09-13"

TERMS_TEXT = """\
By using Weft you, the operator, accept these terms and confirm you will comply with all \
applicable law in the jurisdictions you operate in and investigate.

**Data protection.** Weft processes personal data about identifiable people gathered from open \
sources. This is regulated processing even when the data is already public and even when only \
one person uses the tool. You are responsible for compliance with, as applicable:
- **UK** — the UK GDPR and the Data Protection Act 2018;
- **EU / EEA** — the General Data Protection Regulation (EU) 2016/679;
- **US** — applicable federal and state law, including the Computer Fraud and Abuse Act \
(authorised access only) and state privacy laws such as the CCPA/CPRA.

**Your responsibilities.** You confirm that: (a) you are authorised to carry out this \
reconnaissance; (b) you have a lawful basis for the processing and, where required, a completed \
DPIA and Legitimate Interest Assessment; (c) you will only investigate targets you are \
authorised to investigate and will keep collection proportionate; and (d) you accept full \
responsibility for your use of Weft and its output.

**What Weft does.** Weft aggregates free, public open sources only. It is passive: it does not \
attack, scan, exploit, brute-force, or log in to any system, and it does not access private \
data. Dark-web search, if you enable it, is a passive index query — it does not crawl .onion \
content.

**No warranty.** Weft is provided as-is for authorised reconnaissance. You are solely \
responsible for lawful use. If you do not accept these terms, do not use Weft.\
"""


def _path() -> Path:
    base = os.environ.get("WEFT_HOME")
    root = Path(base) if base else (Path.home() / ".weft")
    return root / "consent.json"


def accepted_record() -> dict | None:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def is_accepted(version: str = TERMS_VERSION) -> bool:
    rec = accepted_record()
    return bool(rec) and rec.get("version") == version


def record_acceptance(operator: str, version: str = TERMS_VERSION) -> dict:
    rec = {"operator": operator or "operator", "version": version,
           "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec), encoding="utf-8")
    return rec
