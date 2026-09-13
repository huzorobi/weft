"""Companies House module against mocked HTTP + fake secrets."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.name.companies_house import CompaniesHouse

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, key="free-key"):
    secrets = FakeSecrets({"COMPANIES_HOUSE_API_KEY": key} if key else {})
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=secrets)


def _name():
    return Entity.make(EntityType.NAME, "Robert Huzo", source_module="seed", confidence=1.0, seed_id="s1")


def _http():
    return FakeHttp({
        "search/officers": (200, {"items": [{
            "title": "HUZO, Robert",
            "address_snippet": "1 High Street, London, E1 1AA",
            "appointment_count": 2,
            "date_of_birth": {"month": 1, "year": 1980},
            "links": {"self": "/officers/ABC123/appointments"},
        }]}),
        "officers/ABC123/appointments": (200, {"items": [{
            "appointed_to": {"company_name": "HUZOSEC LTD", "company_number": "12345678"},
            "officer_role": "director",
            "appointed_on": "2020-01-01",
            "address": {"premises": "1", "address_line_1": "High Street", "locality": "London", "postal_code": "E1 1AA"},
        }]}),
    })


def test_missing_key_disables_module():
    h = asyncio.run(CompaniesHouse().health(_ctx(_http(), key=None)))
    assert not h.ok
    assert "free key" in h.detail


def test_yields_person_company_and_address():
    out = asyncio.run(CompaniesHouse().run(_name(), _ctx(_http())))
    by_type = {}
    for e in out:
        by_type.setdefault(e.type, []).append(e)
    assert any(e.value == "HUZO, Robert" for e in by_type.get(EntityType.PERSON, []))
    orgs = by_type.get(EntityType.ORGANISATION, [])
    assert orgs and orgs[0].value == "HUZOSEC LTD"
    assert orgs[0].metadata["company_number"] == "12345678"
    assert by_type.get(EntityType.ADDRESS), "expected at least one address entity"


def test_no_matches_returns_empty():
    out = asyncio.run(CompaniesHouse().run(_name(), _ctx(FakeHttp({"search/officers": (200, {"items": []})}))))
    assert out == []
