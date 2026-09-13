"""Per-engagement reporting: deterministic Markdown plus a grounded local-AI narrative."""
from weft.reporting.build import build_report
from weft.reporting.kml import build_kml, has_geolocated_ips
from weft.reporting.platforms import classify_platform

__all__ = ["build_report", "classify_platform", "build_kml", "has_geolocated_ips"]
