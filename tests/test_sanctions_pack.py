"""Sanctions & ownership pack — OFAC/UN screening + Companies House PSC (mocked HTTP).

The OFAC CSV and UN XML shapes here are trimmed copies of the live formats verified against
treasury.gov and scsanctions.un.org before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.sanctions.companies_house_psc import CompaniesHousePsc
from weft.modules.sanctions.sanctions_screen import (
    SanctionsScreen,
    match_records,
    parse_ofac_csv,
    parse_un_xml,
)

from _fakes import FakeHttp, FakeSecrets

OFAC_CSV = (
    '36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    '306,"BANCO NACIONAL DE CUBA",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a.k.a. \'BNC\'."\n'
    '2674,"ABBAS, Abu","individual","SDGT","Director",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"DOB 10 Dec 1948"\n'
)

UN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CONSOLIDATED_LIST>
 <INDIVIDUALS>
  <INDIVIDUAL>
   <DATAID>1</DATAID><FIRST_NAME>ERIC</FIRST_NAME><SECOND_NAME>BADEGE</SECOND_NAME>
   <UN_LIST_TYPE>DRC</UN_LIST_TYPE><REFERENCE_NUMBER>CDi.001</REFERENCE_NUMBER>
   <COMMENTS1>Rebel general.</COMMENTS1>
   <INDIVIDUAL_ALIAS><ALIAS_NAME>Eric Baddege</ALIAS_NAME></INDIVIDUAL_ALIAS>
  </INDIVIDUAL>
 </INDIVIDUALS>
 <ENTITIES>
  <ENTITY>
   <DATAID>2</DATAID><FIRST_NAME>ADF GROUP</FIRST_NAME>
   <UN_LIST_TYPE>DRC</UN_LIST_TYPE><REFERENCE_NUMBER>CDe.001</REFERENCE_NUMBER>
  </ENTITY>
 </ENTITIES>
</CONSOLIDATED_LIST>"""


def _ctx(http, secrets=None):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0,
                      http=http, secrets=secrets)


def _name(v, t=EntityType.NAME):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- parsers -----------------------------------------------------------------

def test_parse_ofac_csv_types_programme_aliases():
    recs = parse_ofac_csv(OFAC_CSV)
    by_name = {r.name: r for r in recs}
    assert by_name["AEROCARIBBEAN AIRLINES"].kind is EntityType.ORGANISATION
    assert by_name["AEROCARIBBEAN AIRLINES"].programme == "CUBA"
    assert by_name["ABBAS, Abu"].kind is EntityType.PERSON
    assert "BNC" in by_name["BANCO NACIONAL DE CUBA"].aliases


def test_parse_un_xml_individuals_and_entities():
    recs = parse_un_xml(UN_XML)
    persons = [r for r in recs if r.kind is EntityType.PERSON]
    orgs = [r for r in recs if r.kind is EntityType.ORGANISATION]
    assert persons and persons[0].name == "ERIC BADEGE"
    assert "Eric Baddege" in persons[0].aliases
    assert orgs and orgs[0].name == "ADF GROUP"
    assert orgs[0].programme == "DRC"


# --- matching ----------------------------------------------------------------

def test_match_substring_and_alias_and_token_reorder():
    recs = parse_ofac_csv(OFAC_CSV) + parse_un_xml(UN_XML)
    assert any(r.name == "BANCO NACIONAL DE CUBA" for r in match_records("banco nacional", recs))
    # "Baddege" (double-d) is only in the UN alias, not the primary name "ERIC BADEGE"
    assert any(r.name == "ERIC BADEGE" for r in match_records("Baddege", recs))               # alias-only
    assert any(r.name == "ERIC BADEGE" for r in match_records("Badege Eric", recs))           # reorder


def test_match_ignores_too_short_alias_query():
    # the 'BNC' alias exists but a 3-char query is below the noise floor and must not match
    recs = parse_ofac_csv(OFAC_CSV)
    assert "BNC" in next(r for r in recs if r.name == "BANCO NACIONAL DE CUBA").aliases
    assert match_records("BNC", recs) == []


def test_match_rejects_too_short_or_absent():
    recs = parse_ofac_csv(OFAC_CSV)
    assert match_records("abc", recs) == []       # under min length
    assert match_records("nonexistent-corp", recs) == []


# --- module ------------------------------------------------------------------

def _screen_http():
    return FakeHttp({"ofac/downloads/sdn.csv": (200, OFAC_CSV),
                     "scsanctions.un.org": (200, UN_XML)})


def test_sanctions_module_emits_potential_match_with_provenance():
    out = asyncio.run(SanctionsScreen().run(_name("Banco Nacional de Cuba"), _ctx(_screen_http())))
    assert out and out[0].type is EntityType.ORGANISATION
    md = out[0].metadata
    assert md["sanctioned"] is True and md["match"] == "potential"
    assert md["list"] == "OFAC SDN" and md["programme"] == "CUBA"
    assert md["matched_seed"] == "Banco Nacional de Cuba"


def test_sanctions_module_caches_lists_across_entities():
    http = _screen_http()
    mod = SanctionsScreen()
    asyncio.run(mod.run(_name("Banco Nacional de Cuba"), _ctx(http)))
    asyncio.run(mod.run(_name("ADF Group"), _ctx(http)))
    # two lists fetched exactly once despite two entities
    assert sum(1 for c in http.calls if "sdn.csv" in c) == 1
    assert sum(1 for c in http.calls if "scsanctions" in c) == 1


def test_sanctions_module_clean_name_returns_empty():
    out = asyncio.run(SanctionsScreen().run(_name("Ordinary Person Ltd"), _ctx(_screen_http())))
    assert out == []


# --- Companies House PSC (ownership) -----------------------------------------

def _org_with_number():
    return Entity.make(EntityType.ORGANISATION, "HUZOSEC LTD", source_module="companies_house",
                       confidence=0.8, seed_id="s", metadata={"company_number": "12345678"})


def _psc_http():
    return FakeHttp({"persons-with-significant-control": (200, {"items": [
        {"name": "Robert Huzo", "kind": "individual-person-with-significant-control",
         "nationality": "British", "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
         "address": {"premises": "1", "address_line_1": "High St", "locality": "London", "postal_code": "E1 1AA"}},
        {"name": "Parent Holdings Ltd", "kind": "corporate-entity-person-with-significant-control",
         "natures_of_control": ["ownership-of-shares-75-to-100-percent"]},
    ]})})


def test_psc_missing_key_disables():
    h = asyncio.run(CompaniesHousePsc().health(_ctx(_psc_http(), FakeSecrets({}))))
    assert not h.ok and "free key" in h.detail


def test_psc_yields_beneficial_owners():
    ctx = _ctx(_psc_http(), FakeSecrets({"COMPANIES_HOUSE_API_KEY": "k"}))
    out = asyncio.run(CompaniesHousePsc().run(_org_with_number(), ctx))
    persons = [e for e in out if e.type is EntityType.PERSON]
    orgs = [e for e in out if e.type is EntityType.ORGANISATION]
    assert persons and persons[0].value == "Robert Huzo"
    assert persons[0].metadata["role"] == "beneficial_owner"
    assert persons[0].metadata["controls_company"] == "HUZOSEC LTD"
    assert orgs and orgs[0].value == "Parent Holdings Ltd"   # corporate PSC -> ORGANISATION
    assert any(e.type is EntityType.ADDRESS for e in out)


def test_psc_no_company_number_returns_empty():
    ctx = _ctx(_psc_http(), FakeSecrets({"COMPANIES_HOUSE_API_KEY": "k"}))
    org = Entity.make(EntityType.ORGANISATION, "No Number Ltd", source_module="x", confidence=0.8, seed_id="s")
    assert asyncio.run(CompaniesHousePsc().run(org, ctx)) == []


def test_registry_discovers_sanctions_pack():
    from weft.core import registry
    registry.discover()
    assert {"sanctions_screen", "companies_house_psc"} <= set(registry.registered_classes())
