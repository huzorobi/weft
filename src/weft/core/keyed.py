"""Building block for free-key API sources.

Many free sources need a free (never paid) API key. This base factors the shared wiring so a
keyed source is copy-and-fill: it declares its ``secret_env``, and the base provides the key
lookup and the fail-loud behaviour. The inherited ``health()`` already reports "missing free
key; module disables itself" when the key is absent, so a keyed module never silently looks
like a clean "no results" — it declares itself disabled instead.

A keyed module's ``run`` should start with ``key = self._key(ctx)`` / ``if not key: return []``
and attach the key however the provider expects (a header or a query parameter), using the
helpers here.
"""
from __future__ import annotations

from weft.core.module import Access, Module, RunContext


class KeyedApiModule(Module):
    """Base for a source that needs a free API key.

    Subclasses set ``name``, ``accepts``, ``produces``, ``secret_env`` and implement ``run``.
    ``requires_free_key`` and ``access`` are set here; the inherited ``health()`` self-disables
    without the key.
    """

    requires_free_key = True
    access = Access.FREE_API

    def _key(self, ctx: RunContext | None) -> str | None:
        if ctx is None or ctx.secrets is None or not self.secret_env:
            return None
        return ctx.secrets.get(self.secret_env)

    def _key_header(self, ctx: RunContext | None, header: str, *, prefix: str = "") -> dict | None:
        key = self._key(ctx)
        return {header: f"{prefix}{key}"} if key else None

    def _key_param(self, ctx: RunContext | None, param: str) -> dict | None:
        key = self._key(ctx)
        return {param: key} if key else None
