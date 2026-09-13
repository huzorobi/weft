"""HTTP client used by network modules.

A thin wrapper over ``httpx.AsyncClient`` that follows redirects (RDAP bootstrap
needs it), sets a polite user agent, and returns ``(status, payload)`` tuples so a
module never has to touch the response object. It also offers a small retry for the
GET-JSON path because some free sources (crt.sh in particular) return an empty or
non-JSON body on the first hit and succeed on a retry.

Modules receive an ``HttpClient`` through the run context, so they can be unit tested
against a fake with canned responses and never hit the network.
"""
from __future__ import annotations

import asyncio

import httpx

USER_AGENT = "weft-osint/0.1 (+authorised reconnaissance)"


class HttpxClient:
    def __init__(self, *, timeout: float = 30.0, retries: int = 2):
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        self._retries = retries

    async def get_json(self, url, *, params=None, headers=None, auth=None):
        last_status = 0
        for attempt in range(self._retries + 1):
            resp = await self._client.get(url, params=params, headers=headers, auth=auth)
            last_status = resp.status_code
            if resp.status_code == 200:
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    if attempt < self._retries:
                        await asyncio.sleep(1.0 + attempt)
                        continue
                    return resp.status_code, None
            if resp.status_code in (429, 502, 503) and attempt < self._retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return resp.status_code, None
        return last_status, None

    async def get_text(self, url, *, params=None, headers=None):
        resp = await self._client.get(url, params=params, headers=headers)
        return resp.status_code, resp.text

    async def post_json(self, url, *, json=None, data=None, headers=None):
        """POST a JSON body (``json``) or form body (``data``); return (status, parsed-JSON).

        Some free sources (abuse.ch's ThreatFox/URLhaus) only accept POST. Retries the same
        transient statuses as ``get_json``. Returns ``None`` payload on a non-200 or non-JSON
        response so a module can treat it uniformly with the GET path.
        """
        last_status = 0
        for attempt in range(self._retries + 1):
            resp = await self._client.post(url, json=json, data=data, headers=headers)
            last_status = resp.status_code
            if resp.status_code == 200:
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    return resp.status_code, None
            if resp.status_code in (429, 502, 503) and attempt < self._retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return resp.status_code, None
        return last_status, None

    async def aclose(self):
        await self._client.aclose()
