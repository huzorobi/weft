"""HTML + PDF rendering of the Markdown report."""
from __future__ import annotations

import pytest

from weft.reporting.html import build_html_report, markdown_to_html
from weft.reporting.pdf import build_pdf_from_markdown, pdf_available

MD = """# OSINT reconnaissance report — Acme

## Summary

- 3 entities across 2 types.

## Risk & exposure

- **[Sanctions]** Sanctions match: ACME — Potential match on OFAC SDN _(confidence 0.50)_

## Entities

### email

- `rob@example.com` — confidence 0.90
"""


def test_markdown_to_html_renders_headings_and_lists():
    frag = markdown_to_html(MD)
    assert "<h1>" in frag and "<h2>" in frag
    assert "<li>" in frag and "rob@example.com" in frag


def test_build_html_report_is_self_contained():
    html = build_html_report(MD, title="Acme recon")
    assert html.startswith("<!doctype html>")
    assert "<style>" in html                       # inline CSS, no external deps
    assert "<title>Acme recon</title>" in html
    assert 'id="risk"' in html                     # risk section anchored/styled
    assert "OSINT reconnaissance report" in html


def test_build_html_escapes_title():
    html = build_html_report("# x", title="<script>")
    assert "<title>&lt;script&gt;</title>" in html


@pytest.mark.skipif(not pdf_available(), reason="WeasyPrint not installed")
def test_build_pdf_produces_pdf_bytes():
    data = build_pdf_from_markdown(MD)
    assert data[:5] == b"%PDF-"                    # a real PDF
    assert len(data) > 1000


def test_pdf_error_is_actionable_when_unavailable(monkeypatch):
    import weft.reporting.pdf as pdfmod
    monkeypatch.setattr(pdfmod, "pdf_available", lambda: False)
    with pytest.raises(RuntimeError, match="WeasyPrint"):
        pdfmod.build_pdf_from_html("<html></html>")
