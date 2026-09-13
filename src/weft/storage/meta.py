"""Metadata + audit persistence (Postgres in prod, SQLite for dev).

Holds engagements, runs, and the append-only audit log. The audit table is
insert-only from the application: there is a ``append_audit`` and reads, and no
update/delete path. SQLAlchemy models keep the schema in one place; the dev default
is SQLite so the whole store stands up with no container.

This module is used from Phase 1 onward; Phase 0's fail-closed gate test does not
depend on it (the gate is pure), which is deliberate.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    String,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from weft.compliance.audit import AuditEvent, AuditStore


class Base(DeclarativeBase):
    pass


class EngagementRow(Base):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    client: Mapped[str] = mapped_column(String)
    scope_ref: Mapped[str] = mapped_column(String)
    lawful_basis: Mapped[str] = mapped_column(String)
    authorised_targets: Mapped[list] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    dpia_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    lia_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    controller_role: Mapped[str] = mapped_column(String, default="processor")
    verified_domains: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String)
    operator: Mapped[str] = mapped_column(String)
    seed_key: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="running")


class AuditRow(Base):
    """Append-only. The application never updates or deletes rows here."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    engagement_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    operator: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, index=True)
    source_module: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class MetaStore:
    """Session factory + schema management for the metadata store."""

    def __init__(self, database_url: str = "sqlite:///weft-dev.db"):
        self._engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self._engine)

    def session(self) -> Session:
        return Session(self._engine, future=True)


class SqlAuditStore(AuditStore):
    """Append-only :class:`AuditStore` backed by :class:`MetaStore`."""

    def __init__(self, store: MetaStore):
        self._store = store

    def append(self, event: AuditEvent) -> None:
        with self._store.session() as s:
            s.add(AuditRow(
                ts=event.ts,
                engagement_id=event.engagement_id,
                operator=event.operator,
                action=event.action,
                source_module=event.source_module,
                entity_key=event.entity_key,
                detail=event.detail,
            ))
            s.commit()

    def all(self) -> Iterable[AuditEvent]:
        with self._store.session() as s:
            rows = s.scalars(select(AuditRow).order_by(AuditRow.ts)).all()
            return [
                AuditEvent(
                    ts=r.ts, engagement_id=r.engagement_id, operator=r.operator,
                    action=r.action, source_module=r.source_module,
                    entity_key=r.entity_key, detail=r.detail or {},
                )
                for r in rows
            ]
