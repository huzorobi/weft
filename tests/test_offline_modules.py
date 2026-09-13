"""Offline modules: phonenumbers enrichment and DNS enumeration (resolver stubbed)."""
from __future__ import annotations

import asyncio

import pytest

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.dns_enum import DnsEnum
from weft.modules.phone.phonenumbers_local import PhoneNumbersLocal, _HAVE


def _ctx():
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0)


@pytest.mark.skipif(not _HAVE, reason="phonenumbers not installed")
def test_phone_enrichment_gb_number():
    seed = Entity.make(EntityType.PHONE, "+442079460958", source_module="seed", confidence=1.0, seed_id="s1")
    out = asyncio.run(PhoneNumbersLocal().run(seed, _ctx()))
    assert len(out) == 1
    e = out[0]
    assert e.type is EntityType.PHONE
    assert e.key() == seed.key()  # enrichment merges onto the same node
    assert e.metadata["region_code"] == "GB"
    assert "line_type" in e.metadata
    assert e.metadata["carrier_note"] == "original allocation; may be ported"


def test_dns_enum_maps_records_to_entities():
    class StubDns(DnsEnum):
        def _resolve(self, domain, rtype, *, mx=False):
            return {
                "A": ["93.184.216.34"],
                "AAAA": [],
                "MX": ["mail.example.com"],
                "NS": ["a.iana-servers.net", "b.iana-servers.net"],
                "TXT": ["v=spf1 -all"],
            }.get(rtype, [])

    seed = Entity.make(EntityType.DOMAIN, "example.com", source_module="seed", confidence=1.0, seed_id="s1")
    out = asyncio.run(StubDns().run(seed, _ctx()))
    ips = {e.value for e in out if e.type is EntityType.IP}
    domains = {e.value for e in out if e.type is EntityType.DOMAIN and e.metadata.get("record")}
    txt_node = [e for e in out if e.type is EntityType.DOMAIN and "txt" in e.metadata]
    assert ips == {"93.184.216.34"}
    assert "mail.example.com" in domains
    assert "a.iana-servers.net" in domains
    assert txt_node and txt_node[0].metadata["txt"] == ["v=spf1 -all"]


def test_registry_discovers_all_phase1_modules():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {
        "phonenumbers_local", "dns_enum", "crtsh", "certspotter",
        "rdap_whois", "companies_house", "theharvester",
    } <= names
