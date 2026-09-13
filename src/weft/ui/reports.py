"""Save generated reports to a visible folder.

The Chromium app window has no download bar, so a browser download lands in ~/Downloads with no
visible cue. To make reports easy to find, the UI also writes them to ``~/weft-reports/<id>/``
and shows the operator that path. Returns the directory it wrote to.
"""
from __future__ import annotations

import os
from pathlib import Path


def reports_root() -> Path:
    base = os.environ.get("WEFT_REPORTS_DIR")
    return Path(base) if base else (Path.home() / "weft-reports")


def save_report(engagement_id: str, *, md: str | None = None, html: str | None = None,
                pdf: bytes | None = None) -> str:
    """Write the report formats to ~/weft-reports/<engagement_id>/ and return that directory."""
    out = reports_root() / engagement_id
    out.mkdir(parents=True, exist_ok=True)
    if md is not None:
        (out / f"{engagement_id}-report.md").write_text(md, encoding="utf-8")
    if html is not None:
        (out / f"{engagement_id}-report.html").write_text(html, encoding="utf-8")
    if pdf is not None:
        (out / f"{engagement_id}-report.pdf").write_bytes(pdf)
    return str(out)
