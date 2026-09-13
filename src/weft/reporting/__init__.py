"""Per-engagement reporting: deterministic Markdown plus a grounded local-AI narrative."""
from weft.reporting.build import build_report
from weft.reporting.platforms import classify_platform

__all__ = ["build_report", "classify_platform"]
