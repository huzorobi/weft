"""Engagement lifecycle: retention and purge.

Data is tied to its engagement. When an engagement closes, ``purge_engagement``
removes the personal data and findings but keeps the audit trail defensible: it deletes
run records and exported files, clears the graph, and **redacts** the personal
identifiers inside the audit log (the specific email/name), while keeping who ran what,
when, and against which engagement. Redaction is the sanctioned exception to the
append-only audit rule — a lawful erasure — and the purge itself is recorded as a new
audit event.

``expired_engagements`` / ``flag_expired`` drive a retention job that surfaces
engagements past their end date so they can be purged.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import delete, update

from weft.compliance.audit import AuditLogger
from weft.storage.meta import AuditRow, EngagementRepository, MetaStore, RunRow, SqlAuditStore

REDACTED = "[redacted-on-purge]"


@dataclass
class PurgeResult:
    engagement_id: str
    runs_deleted: int
    audit_rows_redacted: int
    files_removed: int
    graph_cleared: bool

    def summary(self) -> str:
        return (f"purged {self.engagement_id}: {self.runs_deleted} run(s) deleted, "
                f"{self.audit_rows_redacted} audit row(s) redacted, {self.files_removed} file(s) removed, "
                f"graph {'cleared' if self.graph_cleared else 'not cleared'}")


def purge_engagement(
    engagement_id: str,
    *,
    meta_store: MetaStore,
    operator: str = "operator",
    graph=None,
    exports_dir: str = "exports",
    now: datetime | None = None,
) -> PurgeResult:
    """Remove personal data and findings for an engagement; keep the redacted audit trail."""
    now = now or datetime.now(timezone.utc)

    with meta_store.session() as s:
        runs_deleted = s.execute(
            delete(RunRow).where(RunRow.engagement_id == engagement_id)).rowcount or 0
        # redact the personal identifier inside the audit log, keep who/what/when/engagement
        audit_redacted = s.execute(
            update(AuditRow)
            .where(AuditRow.engagement_id == engagement_id, AuditRow.entity_key.is_not(None))
            .values(entity_key=REDACTED)).rowcount or 0
        s.commit()

    files_removed = 0
    eng_dir = Path(exports_dir) / engagement_id
    if eng_dir.exists():
        files_removed = sum(1 for _ in eng_dir.rglob("*") if _.is_file())
        shutil.rmtree(eng_dir, ignore_errors=True)

    graph_cleared = False
    if graph is not None and hasattr(graph, "purge_engagement"):
        try:
            graph.purge_engagement(engagement_id)
            graph_cleared = True
        except Exception:
            graph_cleared = False

    EngagementRepository(meta_store).set_status(engagement_id, "purged")

    # record the erasure itself (append-only): who purged what, when
    AuditLogger(SqlAuditStore(meta_store), clock=lambda: now).record(
        action="purge", engagement_id=engagement_id, operator=operator,
        detail={"runs_deleted": runs_deleted, "audit_redacted": audit_redacted,
                "files_removed": files_removed, "graph_cleared": graph_cleared},
    )

    return PurgeResult(engagement_id, runs_deleted, audit_redacted, files_removed, graph_cleared)


def expired_engagements(repo: EngagementRepository, *, on: date | None = None):
    """Active engagements whose end date has passed."""
    on = on or datetime.now(timezone.utc).date()
    return [e for e in repo.list() if e.status == "active" and e.end_date < on]


def flag_expired(repo: EngagementRepository, *, on: date | None = None) -> list[str]:
    """Mark past-end-date active engagements as 'expired'; return their ids."""
    ids = [e.id for e in expired_engagements(repo, on=on)]
    for eid in ids:
        repo.set_status(eid, "expired")
    return ids
