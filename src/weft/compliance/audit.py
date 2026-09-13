"""The append-only audit log.

Every module call, every gate decision, and every legal acceptance is written here
before the thing it describes happens. This log is what makes the tool defensible,
so it is append-only by contract: the logger exposes ``record`` and reads, and
never an update or delete. Deletion of personal data at engagement close does not
delete this log — purge removes findings and personal data, the audit metadata of
who-ran-what-when is retained under its own policy.

The logger writes through an injected :class:`AuditStore`, so it is testable against
an in-memory store with no database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass(frozen=True)
class AuditEvent:
    ts: datetime
    engagement_id: str | None
    operator: str | None
    action: str                 # e.g. module_run, module_skip, scope_gate, legal_accept
    source_module: str | None
    entity_key: str | None
    detail: dict = field(default_factory=dict)


class AuditStore(Protocol):
    """Append-only persistence for audit events."""

    def append(self, event: AuditEvent) -> None: ...

    def all(self) -> Iterable[AuditEvent]: ...


class InMemoryAuditStore:
    """A process-local append-only store. Used in tests and as a default."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def all(self):
        return tuple(self._events)


class AuditLogger:
    """Write-side of the audit log. Append-only by construction."""

    def __init__(self, store: AuditStore, *, clock=None):
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def record(
        self,
        *,
        action: str,
        engagement_id: str | None = None,
        operator: str | None = None,
        source_module: str | None = None,
        entity_key: str | None = None,
        detail: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            ts=self._clock(),
            engagement_id=engagement_id,
            operator=operator,
            action=action,
            source_module=source_module,
            entity_key=entity_key,
            detail=dict(detail or {}),
        )
        self._store.append(event)
        return event

    def record_gate(self, decision) -> None:
        """Persist every audit event a gate decision produced."""
        for ev in decision.audit_events:
            self.record(
                action=ev.get("action", "scope_gate"),
                engagement_id=ev.get("engagement"),
                operator=ev.get("operator"),
                entity_key=ev.get("seed"),
                detail={k: v for k, v in ev.items()
                        if k not in {"action", "engagement", "operator", "seed"}},
            )

    def events(self):
        return self._store.all()
