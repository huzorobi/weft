"""Engagement lifecycle: purge (redacts audit, deletes runs) and retention."""
from __future__ import annotations

from datetime import date, datetime, timezone

from weft.compliance.audit import AuditEvent
from weft.compliance.engagement import ControllerRole, Engagement
from weft.lifecycle import REDACTED, expired_engagements, flag_expired, purge_engagement
from weft.storage.meta import EngagementRepository, MetaStore, RunRow, SqlAuditStore

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _eng(eid="ENG-1", status="active", end=date(2026, 12, 31)):
    return Engagement(id=eid, client="Acme", scope_ref="S", lawful_basis="LI",
                      authorised_targets=["rob@example.com"], start_date=date(2026, 1, 1), end_date=end,
                      controller_role=ControllerRole.PROCESSOR, status=status)


def _store(tmp_path):
    return MetaStore(f"sqlite:///{tmp_path}/t.db")


def _seed_data(meta, eid):
    # a run row (seed_key is personal data) + audit rows with a personal entity_key
    with meta.session() as s:
        s.add(RunRow(id=f"run-{eid}", engagement_id=eid, operator="rob",
                     seed_key="email:rob@example.com", started_at=NOW, status="done"))
        s.commit()
    store = SqlAuditStore(meta)
    store.append(AuditEvent(ts=NOW, engagement_id=eid, operator="rob", action="module_run",
                            source_module="gravatar", entity_key="email:rob@example.com", detail={}))


def test_purge_deletes_runs_redacts_audit_keeps_trail(tmp_path):
    meta = _store(tmp_path)
    repo = EngagementRepository(meta)
    repo.save(_eng("ENG-1"))
    repo.save(_eng("ENG-2"))
    _seed_data(meta, "ENG-1")
    _seed_data(meta, "ENG-2")

    res = purge_engagement("ENG-1", meta_store=meta, operator="rob", now=NOW)
    assert res.runs_deleted == 1
    assert res.audit_rows_redacted == 1

    events = list(SqlAuditStore(meta).all())
    e1 = [e for e in events if e.engagement_id == "ENG-1"]
    # personal identifier redacted, but who/what/when kept
    module_rows = [e for e in e1 if e.action == "module_run"]
    assert module_rows and module_rows[0].entity_key == REDACTED
    assert module_rows[0].operator == "rob" and module_rows[0].source_module == "gravatar"
    # the purge itself is recorded
    assert any(e.action == "purge" for e in e1)
    # engagement marked purged
    assert repo.get("ENG-1").status == "purged"


def test_purge_leaves_other_engagements_untouched(tmp_path):
    meta = _store(tmp_path)
    repo = EngagementRepository(meta)
    repo.save(_eng("ENG-1"))
    repo.save(_eng("ENG-2"))
    _seed_data(meta, "ENG-1")
    _seed_data(meta, "ENG-2")
    purge_engagement("ENG-1", meta_store=meta, now=NOW)
    e2 = [e for e in SqlAuditStore(meta).all() if e.engagement_id == "ENG-2" and e.action == "module_run"]
    assert e2 and e2[0].entity_key == "email:rob@example.com"   # untouched
    assert repo.get("ENG-2").status == "active"


def test_purge_removes_export_files(tmp_path):
    meta = _store(tmp_path)
    EngagementRepository(meta).save(_eng("ENG-1"))
    exports = tmp_path / "exports" / "ENG-1"
    exports.mkdir(parents=True)
    (exports / "report.md").write_text("personal data")
    res = purge_engagement("ENG-1", meta_store=meta, exports_dir=str(tmp_path / "exports"), now=NOW)
    assert res.files_removed == 1
    assert not exports.exists()


def test_expired_and_flag(tmp_path):
    meta = _store(tmp_path)
    repo = EngagementRepository(meta)
    repo.save(_eng("PAST", end=date(2026, 1, 31)))
    repo.save(_eng("CURRENT", end=date(2026, 12, 31)))
    exp = expired_engagements(repo, on=date(2026, 9, 13))
    assert [e.id for e in exp] == ["PAST"]
    assert flag_expired(repo, on=date(2026, 9, 13)) == ["PAST"]
    assert repo.get("PAST").status == "expired"
    assert repo.get("CURRENT").status == "active"
