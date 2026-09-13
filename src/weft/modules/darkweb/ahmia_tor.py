"""Dark-web search via Ahmia over Tor (opt-in, search-only).

Queries the Ahmia search engine's onion service through a local Tor SOCKS proxy and
returns the .onion sites and snippets that mention the seed — a real dark-web signal
without connecting to arbitrary hidden services. It is SEARCH-ONLY: it reads Ahmia's
result page; it does NOT crawl or fetch the .onion sites it finds, which is where the
legal and content-exposure risk sits.

Gated twice: it is a ``dark_web`` module (off unless the operator enables the dark-web
toggle) and it self-disables unless a Tor SOCKS proxy is reachable. Requires ``socksio``.
"""
from __future__ import annotations

import os
import re
import socket
import urllib.parse
from html import unescape

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

# Ahmia's official onion search service.
AHMIA_HOST = "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"
AHMIA_ROOT = AHMIA_HOST + "/"
AHMIA_SEARCH = AHMIA_HOST + "/search/"
DEFAULT_PROXY = "socks5://127.0.0.1:9050"
_ONION_RE = re.compile(r"[a-z2-7]{16,56}\.onion", re.I)
_AHMIA_HOST = "juhanurmihxlp77"
_HIDDEN_RE = re.compile(r'<input type="hidden" name="([^"]+)" value="([^"]+)"')


@register
class DarkWebAhmia(Module):
    name = "darkweb_ahmia"
    accepts = [EntityType.DOMAIN, EntityType.EMAIL, EntityType.NAME,
               EntityType.USERNAME, EntityType.ORGANISATION]
    produces = [EntityType.ARCHIVE_SNAPSHOT, EntityType.URL]
    access = Access.SELF_HOSTED
    dark_web = True
    reliability = 0.4
    timeout_s = 120

    def _proxy(self) -> str:
        return os.getenv("DARKWEB_TOR_PROXY", DEFAULT_PROXY)

    async def health(self, ctx=None):
        proxy = self._proxy()
        m = re.search(r"://([^:/]+):(\d+)", proxy)
        if not m:
            return HealthStatus.down(f"bad Tor proxy '{proxy}'")
        host, port = m.group(1), int(m.group(2))
        try:
            with socket.create_connection((host, port), timeout=3):
                return HealthStatus.up(f"Tor SOCKS reachable at {host}:{port}")
        except Exception:
            return HealthStatus.down(f"Tor SOCKS not reachable at {host}:{port} — start Tor to enable dark-web search")

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        try:
            import httpx
        except Exception:
            return []
        try:
            # Ahmia's search form carries a per-session hidden token + cookie; a bare query is
            # bounced to the homepage. Fetch home first, carry the cookie, replay the token.
            async with httpx.AsyncClient(proxy=self._proxy(), timeout=self.timeout_s,
                                         follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0"}) as client:
                home = await client.get(AHMIA_ROOT)
                params = {"q": entity.value}
                if home.status_code == 200:
                    tok = _HIDDEN_RE.search(home.text)
                    if tok:
                        params[tok.group(1)] = tok.group(2)
                resp = await client.get(AHMIA_SEARCH, params=params)
        except Exception:
            return []
        if resp.status_code != 200:
            return []
        out: list[Entity] = []
        for onion_url, title in _parse_ahmia(resp.text):
            out.append(Entity.make(EntityType.ARCHIVE_SNAPSHOT, onion_url, source_module=self.name,
                                   confidence=self.reliability, seed_id=entity.seed_id,
                                   metadata={"source": "dark web (Ahmia via Tor)", "title": title or None,
                                             "mentions": entity.value}, label=title or None))
        return out


def _parse_ahmia(html: str) -> list[tuple[str, str]]:
    """Extract (onion url, title) from an Ahmia results page. Search-only, no fetching."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    # Ahmia renders each hit as a block; split on the result marker and parse each.
    blocks = re.split(r'class="result"', html)
    for block in blocks[1:]:
        # onion URL from a <cite> or a redirect_url= param
        cite = re.search(r"<cite[^>]*>\s*(https?://[a-z2-7]{16,56}\.onion[^\s<]*)", block, re.I)
        url = cite.group(1) if cite else None
        if not url:
            red = re.search(r"redirect_url=([^\"'&]+)", block)
            if red:
                url = urllib.parse.unquote(red.group(1))
        if not url:
            continue
        host_m = _ONION_RE.search(url)
        if not host_m or _AHMIA_HOST in host_m.group(0) or host_m.group(0) in seen:
            continue
        seen.add(host_m.group(0))
        title_m = re.search(r"<a[^>]*>([^<]+)</a>", block)
        title = unescape(title_m.group(1).strip()) if title_m else ""
        out.append((url, title))
    return out
