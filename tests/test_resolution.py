"""Entity resolution: handle extraction, shared-handle clusters, name folding, leads."""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.graphstore import InMemoryGraph
from weft.core.resolution import handle_of, resolve_identities


def _e(etype, val, src="m"):
    return Entity.make(etype, val, source_module=src, confidence=0.9, seed_id="s")


def test_handle_of():
    assert handle_of(_e(EntityType.USERNAME, "@Rob")) == "rob"
    assert handle_of(_e(EntityType.EMAIL, "Rob.H@example.com")) == "rob.h"
    assert handle_of(_e(EntityType.SOCIAL_PROFILE, "https://github.com/torvalds")) == "torvalds"
    assert handle_of(_e(EntityType.SOCIAL_PROFILE, "https://medium.com/@rob")) == "rob"
    assert handle_of(_e(EntityType.NAME, "Robert Huzo")) is None


def test_shared_handle_cluster():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://github.com/rob"))
    g.upsert_entity(_e(EntityType.USERNAME, "rob"))
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://twitter.com/rob"))
    res = resolve_identities(g)
    assert res.clusters and res.clusters[0].label == "rob"
    assert res.clusters[0].size >= 3


def test_name_folded_into_handle_cluster():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://github.com/roberthuzo"))
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://gitlab.com/roberthuzo"))
    g.upsert_entity(_e(EntityType.NAME, "Robert Huzo"))
    res = resolve_identities(g)
    c = res.clusters[0]
    assert "name 'Robert Huzo'" in c.basis
    assert any(k.startswith("name:") for k in c.keys)


def test_possibly_same_fuzzy_names():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.NAME, "Robert Huzo"))
    g.upsert_entity(_e(EntityType.NAME, "Robert Huzoo"))
    res = resolve_identities(g)
    assert res.possibly_same and res.possibly_same[0][2] >= 0.86


def test_no_cluster_for_unique_handles():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.USERNAME, "alice"))
    g.upsert_entity(_e(EntityType.USERNAME, "bob"))
    assert resolve_identities(g).clusters == []


def test_report_includes_identity_clusters():
    from datetime import date
    from weft.compliance.engagement import ControllerRole, Engagement
    from weft.core.reasoner import NullReasoner
    from weft.reporting.build import build_report
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.SOCIAL_PROFILE, "https://github.com/rob"))
    g.upsert_entity(_e(EntityType.USERNAME, "rob"))
    eng = Engagement(id="E", client="Acme", scope_ref="S", lawful_basis="LI", authorised_targets=["x"],
                     start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), controller_role=ControllerRole.PROCESSOR)
    md = build_report(eng, g, reasoner=NullReasoner())
    assert "## Identity clusters" in md
    assert "shared handle 'rob'" in md


def _em(etype, val, meta, src="pgp_keyservers"):
    return Entity.make(etype, val, source_module=src, confidence=0.8, seed_id="s", metadata=meta)


def test_shared_pgp_key_creates_strong_cluster():
    g = InMemoryGraph()
    # seed email + an alias email + a name, all bound to the seed's PGP key
    g.upsert_entity(_e(EntityType.EMAIL, "torvalds@kernel.org"))
    g.upsert_entity(_em(EntityType.EMAIL, "torvalds@linux-foundation.org",
                        {"linked_via": "shared PGP key", "with_email": "torvalds@kernel.org"}))
    g.upsert_entity(_em(EntityType.NAME, "Linus Torvalds",
                        {"linked_via": "PGP key uid", "for_email": "torvalds@kernel.org"}))
    res = resolve_identities(g)
    pgp = [c for c in res.clusters if c.label.startswith("pgp:")]
    assert pgp, "expected a PGP-key cluster"
    c = pgp[0]
    assert c.confidence == 0.9 and "cryptographic" in c.basis
    assert "email:torvalds@kernel.org" in c.keys              # anchor email folded in
    assert "email:torvalds@linux-foundation.org" in c.keys    # alias
    assert any(k.startswith("name:") for k in c.keys)          # name uid


def test_no_pgp_metadata_no_strong_cluster():
    g = InMemoryGraph()
    g.upsert_entity(_e(EntityType.EMAIL, "a@x.com"))
    g.upsert_entity(_e(EntityType.EMAIL, "b@x.com"))
    res = resolve_identities(g)
    assert not any(c.label.startswith("pgp:") for c in res.clusters)
