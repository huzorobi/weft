"""Phase 2 UI services: engagement repo, graph payload, run service. No Streamlit."""
from __future__ import annotations

from datetime import date

from weft.compliance.audit import InMemoryAuditStore
from weft.compliance.engagement import ControllerRole, Engagement
from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.storage.meta import EngagementRepository, MetaStore
from weft.ui.graphview import build_vis_payload, colour_for
from weft.ui.runner import execute_run

from _fakes import StaticModule


def _eng(**over):
    kw = dict(
        id="ENG-1", client="Acme", scope_ref="SOW-1", lawful_basis="LI",
        authorised_targets=["example.com"], start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        dpia_ref="D1", lia_ref="L1", controller_role=ControllerRole.PROCESSOR,
        verified_domains={"example.com": "proof"},
    )
    kw.update(over)
    return Engagement(**kw)


# --- engagement repository -------------------------------------------------

def test_engagement_repo_roundtrip(tmp_path):
    repo = EngagementRepository(MetaStore(f"sqlite:///{tmp_path}/t.db"))
    e = _eng()
    repo.save(e)
    got = repo.get("ENG-1")
    assert got is not None
    assert got.client == "Acme"
    assert got.authorised_targets == ["example.com"]
    assert got.controller_role is ControllerRole.PROCESSOR
    assert got.verified_domains == {"example.com": "proof"}
    assert [x.id for x in repo.list()] == ["ENG-1"]


def test_engagement_repo_update_in_place(tmp_path):
    repo = EngagementRepository(MetaStore(f"sqlite:///{tmp_path}/t.db"))
    repo.save(_eng())
    repo.save(_eng(client="NewCo"))
    assert repo.get("ENG-1").client == "NewCo"
    assert len(repo.list()) == 1


# --- graph payload ---------------------------------------------------------

def _graph_with_confidences():
    g = InMemoryGraph()
    hi = Entity.make(EntityType.DOMAIN, "hi.example.com", source_module="m", confidence=0.9, seed_id="s")
    lo = Entity.make(EntityType.DOMAIN, "lo.example.com", source_module="m", confidence=0.2, seed_id="s")
    g.upsert_entity(hi)
    g.upsert_entity(lo)
    g.link(hi, lo, via="m", confidence=0.2)
    return g, hi, lo


def test_payload_lists_nodes_and_edges():
    g, hi, lo = _graph_with_confidences()
    p = build_vis_payload(g)
    assert len(p["nodes"]) == 2
    assert len(p["edges"]) == 1


def test_confidence_filter_drops_low_nodes_and_their_edges():
    g, hi, lo = _graph_with_confidences()
    p = build_vis_payload(g, min_confidence=0.5)
    ids = {n["id"] for n in p["nodes"]}
    assert ids == {hi.key()}
    assert p["edges"] == []  # edge to the dropped low node is gone


def test_colour_is_stable_per_type():
    assert colour_for(EntityType.DOMAIN) == colour_for(EntityType.DOMAIN)
    assert colour_for(EntityType.DOMAIN) != colour_for(EntityType.EMAIL)


# --- run service -----------------------------------------------------------

def _child(v):
    return Entity.make(EntityType.DOMAIN, v, source_module="m", confidence=0.9, seed_id="s")


def test_execute_run_refuses_without_acceptance():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com")])
    out = execute_run(engagement=_eng(), seed_type=EntityType.DOMAIN, seed_value="example.com",
                      operator="rob", depth_cap=2, allow_tos_risk=False, accepted=False, modules=[m])
    assert out.accepted is False
    assert out.graph.nodes == {}
    assert "not accepted" in out.message


def test_execute_run_accepted_populates_graph_and_audit():
    store = InMemoryAuditStore()
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com"), _child("b.example.com")])
    out = execute_run(engagement=_eng(), seed_type=EntityType.DOMAIN, seed_value="example.com",
                      operator="rob", depth_cap=2, allow_tos_risk=False, accepted=True,
                      modules=[m], audit_store=store)
    assert out.accepted
    assert "domain:a.example.com" in out.graph.nodes
    actions = {e.action for e in store.all()}
    assert "legal_accept" in actions
    assert "module_run" in actions


def test_execute_run_out_of_scope_seed_is_refused():
    m = StaticModule("m", [EntityType.DOMAIN], [_child("a.example.com")])
    out = execute_run(engagement=_eng(), seed_type=EntityType.DOMAIN, seed_value="not-in-scope.net",
                      operator="rob", depth_cap=2, allow_tos_risk=False, accepted=True, modules=[m])
    assert out.result.seeds_refused
    assert "refused" in out.message.lower()
