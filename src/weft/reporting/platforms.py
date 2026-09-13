"""Classify a social/profile URL by platform, so the report can group presence.

Purely host-based and deterministic. These profiles are surfaced by the open
enumeration modules (maigret, sherlock, holehe, gravatar, the SearXNG footprint) that
hit each platform's PUBLIC pages — Weft does not scrape the platforms directly.
"""
from __future__ import annotations

from urllib.parse import urlsplit

# host substring -> canonical platform label
_PLATFORMS = {
    "facebook.com": "Facebook", "fb.com": "Facebook",
    "twitter.com": "X (Twitter)", "x.com": "X (Twitter)",
    "linkedin.com": "LinkedIn",
    "github.com": "GitHub", "gitlab.com": "GitLab",
    "instagram.com": "Instagram",
    "reddit.com": "Reddit",
    "youtube.com": "YouTube", "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "mastodon": "Mastodon",
    "t.me": "Telegram", "telegram.me": "Telegram",
    "medium.com": "Medium",
    "pinterest.": "Pinterest",
    "tumblr.com": "Tumblr",
    "keybase.io": "Keybase",
    "gravatar.com": "Gravatar",
    "stackoverflow.com": "Stack Overflow", "stackexchange.com": "Stack Exchange",
}


def classify_platform(value: str) -> str | None:
    """Return a platform label for a URL/handle, or None if it is not a known platform."""
    if not value:
        return None
    host = (urlsplit(value).hostname or value).lower()
    for frag, label in _PLATFORMS.items():
        if frag in host or frag in value.lower():
            return label
    return None
