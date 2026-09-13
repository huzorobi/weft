"""The module contract every source implements.

A module queries one free source for one entity and returns new entities. The
interface is identical across sources so adding one is copy-and-fill.

Several "offline" sources are really external tools or binaries (maigret, holehe,
theHarvester, phoneinfoga), not simple async functions. So the base contract carries
tool concerns from the start: a declared required binary, a version, a per-call
timeout, and a ``health()`` check. A module that cannot run (missing binary, missing
free key, dead endpoint) must report that *loudly* through ``health()`` rather than
silently returning ``[]`` and looking like a clean "no results".
"""
from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from weft.core.entity import Entity, EntityType

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


class Access(str, Enum):
    OFFLINE = "offline"          # runs locally, no network account
    FREE_API = "free_api"        # free endpoint, may need a free key, may be rate-limited
    SELF_HOSTED = "self_hosted"  # free because we run it (e.g. SearXNG)


@dataclass
class HealthStatus:
    """The result of a module self-check."""

    ok: bool
    detail: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def up(cls, detail: str = "ready") -> "HealthStatus":
        return cls(ok=True, detail=detail)

    @classmethod
    def down(cls, detail: str) -> "HealthStatus":
        return cls(ok=False, detail=detail)


class RateLimiter(Protocol):
    async def acquire(self, key: str) -> None: ...


class SecretsAccessor(Protocol):
    def get(self, name: str) -> str | None: ...


class AuditSink(Protocol):
    def record(self, **fields: object) -> None: ...


class HttpClient(Protocol):
    async def get_json(
        self, url: str, *, params: dict | None = None,
        headers: dict | None = None, auth: tuple[str, str] | None = None,
    ) -> tuple[int, object]: ...

    async def get_text(
        self, url: str, *, params: dict | None = None, headers: dict | None = None,
    ) -> tuple[int, str]: ...


@dataclass
class RunContext:
    """Everything a module needs from the run it is part of.

    Dependencies are injected so modules stay pure and offline-testable: give the
    context canned rate limiter / secrets / audit / http and a module can be unit
    tested with no network and no binaries.
    """

    engagement_id: str
    operator: str
    allow_tos_risk: bool
    depth: int
    allow_dark_web: bool = False
    rate_limiter: RateLimiter | None = None
    secrets: SecretsAccessor | None = None
    audit: AuditSink | None = None
    http: HttpClient | None = None


class Module(ABC):
    """Base class for every source module."""

    name: str
    accepts: list[EntityType]
    produces: list[EntityType]
    access: Access
    requires_free_key: bool = False   # free to obtain, never paid
    tos_risk: bool = False
    dark_web: bool = False            # queries the dark web (Tor); gated by its own opt-in
    reliability: float = 0.5          # source-reliability weight (0-1) for confidence scoring

    # Tool concerns, so an external-binary module cannot no-op silently.
    version: str | None = None
    timeout_s: int = 60
    requires_binary: str | None = None   # name of a CLI binary that must be on PATH
    secret_env: str | None = None        # env var holding the free key, if requires_free_key

    async def health(self, ctx: RunContext | None = None) -> HealthStatus:
        """Default health check: binary present and free key available if required.

        Override to add a live endpoint probe. Keep it cheap and side-effect-free.
        """
        if self.requires_binary and shutil.which(self.requires_binary) is None:
            return HealthStatus.down(f"required binary '{self.requires_binary}' not found on PATH")
        if self.requires_free_key:
            key = None
            if ctx is not None and ctx.secrets is not None and self.secret_env:
                key = ctx.secrets.get(self.secret_env)
            if not key:
                env = self.secret_env or "<free key>"
                return HealthStatus.down(f"missing free key ({env}); module disables itself")
        return HealthStatus.up()

    @abstractmethod
    async def run(self, entity: Entity, ctx: RunContext) -> list[Entity]:
        """Query the source for one entity. Return new entities with source and
        confidence set. Must be idempotent. Never raise on 'no results' — return []."""
        ...

    def can_run(self, entity: Entity, *, allow_tos_risk: bool, allow_dark_web: bool = False) -> bool:
        """Bus predicate: type accepted, and the ToS and dark-web opt-ins satisfied."""
        if entity.type not in self.accepts:
            return False
        if self.tos_risk and not allow_tos_risk:
            return False
        if self.dark_web and not allow_dark_web:
            return False
        return True
