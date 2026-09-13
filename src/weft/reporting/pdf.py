"""Render the HTML report to PDF via WeasyPrint.

WeasyPrint is an optional dependency (it needs system libraries). It is imported lazily so the
rest of the reporting stack works without it; ``pdf_available()`` reports whether it can run,
and ``build_pdf`` raises a clear, actionable error if it cannot.
"""
from __future__ import annotations

from weft.reporting.html import build_html_report


def pdf_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


def build_pdf_from_html(html: str) -> bytes:
    if not pdf_available():
        raise RuntimeError("PDF export needs WeasyPrint: pip install weasyprint (plus its system libs).")
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()


def build_pdf_from_markdown(md_text: str, *, title: str = "Weft OSINT report") -> bytes:
    return build_pdf_from_html(build_html_report(md_text, title=title))


def write_pdf(md_text: str, path: str, *, title: str = "Weft OSINT report") -> str:
    with open(path, "wb") as fh:
        fh.write(build_pdf_from_markdown(md_text, title=title))
    return path
