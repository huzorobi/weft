"""Shared helpers for the GitHub API modules (no module registered here)."""
from __future__ import annotations

GITHUB_API = "https://api.github.com"


def gh_headers(token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
