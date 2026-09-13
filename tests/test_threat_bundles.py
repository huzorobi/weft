"""Threat-intel bundles — DNS-filter reputation + IP blocklist membership (mocked HTTP).

DoH JSON and blocklist shapes here mirror the live responses verified against dns.google,
family.cloudflare-dns.com, and the public blocklist feeds before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.threat.dns_reputation import DnsReputation
from weft.modules.threat.ip_blocklists import IpBlocklists, parse_cidr_list, parse_ip_list

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _domain(v="malware.example"):
    return Entity.make(EntityType.DOMAIN, v, source_module="seed", confidence=1.0, seed_id="s")


def _ip(v="1.2.3.4"):
    return Entity.make(EntityType.IP, v, source_module="seed", confidence=1.0, seed_id="s")


# --- DNS reputation ----------------------------------------------------------

def _doh(status, answers):
    return (200, {"Status": status, "Answer": [{"type": 1, "data": a} for a in answers]})


def test_dns_reputation_flags_domain_blocked_by_filter():
    http = FakeHttp({
        "dns.google/resolve": _doh(0, ["93.184.216.34"]),                 # neutral resolves
        "family.cloudflare-dns.com": _doh(0, ["0.0.0.0"]),                # family sinkholes -> blocked
        "dns.adguard-dns.com": _doh(0, ["93.184.216.34"]),               # adguard allows
    })
    out = asyncio.run(DnsReputation().run(_domain(), _ctx(http)))
    assert out and out[0].type is EntityType.DOMAIN
    assert out[0].metadata["reputation"] == "flagged"
    assert out[0].metadata["blocked_by"] == ["cloudflare_family"]


def test_dns_reputation_nxdomain_from_filter_is_a_block():
    http = FakeHttp({
        "dns.google/resolve": _doh(0, ["93.184.216.34"]),
        "family.cloudflare-dns.com": _doh(3, []),                         # NXDOMAIN -> blocked
        "dns.adguard-dns.com": _doh(3, []),
    })
    out = asyncio.run(DnsReputation().run(_domain(), _ctx(http)))
    assert set(out[0].metadata["blocked_by"]) == {"cloudflare_family", "adguard"}
    assert out[0].confidence > 0.6   # two filters -> higher confidence


def test_dns_reputation_clean_domain_returns_empty():
    http = FakeHttp({
        "dns.google/resolve": _doh(0, ["93.184.216.34"]),
        "family.cloudflare-dns.com": _doh(0, ["93.184.216.34"]),
        "dns.adguard-dns.com": _doh(0, ["93.184.216.34"]),
    })
    assert asyncio.run(DnsReputation().run(_domain(), _ctx(http))) == []


def test_dns_reputation_no_neutral_answer_cannot_assess():
    # if the neutral resolver has no real address, a filter's null answer proves nothing
    http = FakeHttp({
        "dns.google/resolve": _doh(3, []),
        "family.cloudflare-dns.com": _doh(3, []),
    })
    assert asyncio.run(DnsReputation().run(_domain(), _ctx(http))) == []


# --- IP blocklists -----------------------------------------------------------

def test_parsers_skip_comments_and_bad_lines():
    assert parse_ip_list("# header\n1.2.3.4\nnot-an-ip\n5.6.7.8 90\n") == {"1.2.3.4", "5.6.7.8"}
    nets = parse_cidr_list("; comment\n10.0.0.0/8 ; SBL1\nbad/33\n")
    assert len(nets) == 1 and str(nets[0]) == "10.0.0.0/8"


def _blocklist_http():
    return FakeHttp({
        "levels/3.txt": (200, "1.2.3.4\n9.9.9.9\n"),
        "blocklist.de": (200, "1.2.3.4\n"),
        "cinsscore": (200, "8.8.8.8\n"),
        "greensnow": (200, "\n"),
        "spamhaus.org/drop": (200, "1.2.0.0/16 ; SBL999\n"),
    })


def test_ip_blocklists_reports_lists_and_scales_confidence():
    out = asyncio.run(IpBlocklists().run(_ip("1.2.3.4"), _ctx(_blocklist_http())))
    assert out and out[0].type is EntityType.IP
    md = out[0].metadata
    assert set(md["on_blocklists"]) == {"ipsum_l3", "blocklist_de", "spamhaus_drop"}  # exact + exact + CIDR
    assert md["list_count"] == 3
    assert out[0].confidence > 0.75


def test_ip_blocklists_clean_ip_returns_empty():
    assert asyncio.run(IpBlocklists().run(_ip("203.0.113.7"), _ctx(_blocklist_http()))) == []


def test_ip_blocklists_caches_across_entities():
    http = _blocklist_http()
    mod = IpBlocklists()
    asyncio.run(mod.run(_ip("1.2.3.4"), _ctx(http)))
    asyncio.run(mod.run(_ip("9.9.9.9"), _ctx(http)))
    assert sum(1 for c in http.calls if "levels/3.txt" in c) == 1   # fetched once, not per entity


def test_registry_discovers_threat_bundles():
    from weft.core import registry
    registry.discover()
    assert {"dns_reputation", "ip_blocklists"} <= set(registry.registered_classes())
