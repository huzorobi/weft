"""Report saving to a visible folder."""
from __future__ import annotations

from weft.ui import reports


def test_save_report_writes_all_formats(tmp_path, monkeypatch):
    monkeypatch.setenv("WEFT_REPORTS_DIR", str(tmp_path))
    d = reports.save_report("WEFT-X", md="# hi", html="<h1>hi</h1>", pdf=b"%PDF-1.4 x")
    from pathlib import Path
    p = Path(d)
    assert (p / "WEFT-X-report.md").read_text() == "# hi"
    assert (p / "WEFT-X-report.html").read_text() == "<h1>hi</h1>"
    assert (p / "WEFT-X-report.pdf").read_bytes().startswith(b"%PDF")


def test_save_report_skips_missing_formats(tmp_path, monkeypatch):
    monkeypatch.setenv("WEFT_REPORTS_DIR", str(tmp_path))
    d = reports.save_report("WEFT-Y", md="only md", html=None, pdf=None)
    from pathlib import Path
    assert (Path(d) / "WEFT-Y-report.md").exists()
    assert not (Path(d) / "WEFT-Y-report.pdf").exists()
