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
from weft.compliance.engagement import ControllerRole, Engagement


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


class EngagementRepository:
    """Persist and load :class:`Engagement` domain objects via :class:`MetaStore`."""

    def __init__(self, store: MetaStore):
        self._store = store

    def save(self, e: Engagement) -> None:
        with self._store.session() as s:
            row = s.get(EngagementRow, e.id) or EngagementRow(id=e.id)
            row.client = e.client
            row.scope_ref = e.scope_ref
            row.lawful_basis = e.lawful_basis
            row.authorised_targets = list(e.authorised_targets)
            row.start_date = e.start_date
            row.end_date = e.end_date
            row.dpia_ref = e.dpia_ref
            row.lia_ref = e.lia_ref
            row.controller_role = e.controller_role.value
            row.verified_domains = dict(e.verified_domains)
            row.status = e.status
            s.add(row)
            s.commit()

    def get(self, engagement_id: str) -> Engagement | None:
        with self._store.session() as s:
            row = s.get(EngagementRow, engagement_id)
            return self._to_domain(row) if row else None

    def list(self) -> list[Engagement]:
        with self._store.session() as s:
            rows = s.scalars(select(EngagementRow).order_by(EngagementRow.id)).all()
            return [self._to_domain(r) for r in rows]

    @staticmethod
    def _to_domain(row: EngagementRow) -> Engagement:
        return Engagement(
            id=row.id,
            client=row.client,
            scope_ref=row.scope_ref,
            lawful_basis=row.lawful_basis,
            authorised_targets=list(row.authorised_targets or []),
            start_date=row.start_date,
            end_date=row.end_date,
            dpia_ref=row.dpia_ref,
            lia_ref=row.lia_ref,
            controller_role=ControllerRole(row.controller_role),
            verified_domains=dict(row.verified_domains or {}),
            status=row.status,
        )

    def set_status(self, engagement_id: str, status: str) -> None:
        with self._store.session() as s:
            row = s.get(EngagementRow, engagement_id)
            if row:
                row.status = status
                s.add(row)
                s.commit()
