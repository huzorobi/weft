"""Phase 3 account-enumeration modules against mocked HTTP / sample tool output."""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.domain.github_domain import GithubDomain
from weft.modules.email.github_email import GithubEmail
from weft.modules.email.gravatar import Gravatar
from weft.modules.email.holehe import _parse_holehe
from weft.modules.username.github_user import GithubUser
from weft.modules.username.maigret import _parse_maigret

from _fakes import FakeHttp, FakeSecrets


def _ctx(http, token=None):
    secrets = FakeSecrets({"GITHUB_TOKEN": token} if token else {})
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=True, depth=0,
                      http=http, secrets=secrets)


def _e(etype, value):
    return Entity.make(etype, value, source_module="seed", confidence=1.0, seed_id="s1")


# --- gravatar --------------------------------------------------------------

def test_gravatar_parses_accounts_urls_name():
    http = FakeHttp({"gravatar.com": (200, {"entry": [{
        "displayName": "Rob",
        "accounts": [{"url": "https://twitter.com/rob", "shortname": "twitter",
                      "username": "rob", "verified": True}],
        "urls": [{"value": "https://rob.example", "title": "Blog"}],
    }]})})
    out = asyncio.run(Gravatar().run(_e(EntityType.EMAIL, "rob@example.com"), _ctx(http)))
    types = {e.type for e in out}
    assert EntityType.NAME in types
    assert EntityType.SOCIAL_PROFILE in types
    assert EntityType.USERNAME in types
    assert EntityType.URL in types


def test_gravatar_404_returns_empty():
    out = asyncio.run(Gravatar().run(_e(EntityType.EMAIL, "none@example.com"),
                                     _ctx(FakeHttp({"gravatar.com": (404, None)}))))
    assert out == []


# --- github user -----------------------------------------------------------

def test_github_user_parses_profile():
    http = FakeHttp({"/users/torvalds": (200, {
        "login": "torvalds", "name": "Linus Torvalds", "email": "linus@example.com",
        "html_url": "https://github.com/torvalds", "blog": "https://blog.example",
        "company": "Linux Foundation", "twitter_username": "linus",
    })})
    out = asyncio.run(GithubUser().run(_e(EntityType.USERNAME, "torvalds"), _ctx(http)))
    by = {(e.type, e.value) for e in out}
    assert (EntityType.NAME, "Linus Torvalds") in by
    assert (EntityType.EMAIL, "linus@example.com") in by
    assert (EntityType.ORGANISATION, "Linux Foundation") in by
    assert any(e.type is EntityType.USERNAME and e.value == "linus" for e in out)


# --- github email (needs token) --------------------------------------------

def test_github_email_disabled_without_token():
    h = asyncio.run(GithubEmail().health(_ctx(FakeHttp({}), token=None)))
    assert not h.ok and "free key" in h.detail


def test_github_email_parses_commits():
    http = FakeHttp({"search/commits": (200, {"items": [
        {"author": {"login": "rob"}, "repository": {"html_url": "https://github.com/rob/repo"},
         "commit": {"author": {"name": "Rob H"}}},
    ]})})
    out = asyncio.run(GithubEmail().run(_e(EntityType.EMAIL, "rob@example.com"), _ctx(http, token="t")))
    assert any(e.type is EntityType.USERNAME and e.value == "rob" for e in out)
    assert any(e.type is EntityType.URL for e in out)


# --- github domain (needs token) -------------------------------------------

def test_github_domain_parses_code_hits():
    http = FakeHttp({"search/code": (200, {"items": [
        {"html_url": "https://github.com/x/y/blob/f", "repository": {"full_name": "x/y"}},
    ]})})
    out = asyncio.run(GithubDomain().run(_e(EntityType.DOMAIN, "example.com"), _ctx(http, token="t")))
    assert out and out[0].type is EntityType.URL
    assert out[0].metadata["repo"] == "x/y"


# --- external-tool parsers -------------------------------------------------

def test_holehe_parser_keeps_only_used():
    out = _parse_holehe("[+] github.com\n[-] nope.com\n[+] twitter.com\n[x] rate.com\n")
    assert out == ["github.com", "twitter.com"]


def test_maigret_parser_keeps_claimed_only():
    data = {
        "GitHub": {"status": {"status": "Claimed"}, "url_user": "https://github.com/rob"},
        "Twitter": {"status": {"status": "Available"}, "url_user": "https://twitter.com/rob"},
    }
    out = _parse_maigret(data, _e(EntityType.USERNAME, "rob"), "maigret", 0.6)
    assert len(out) == 1
    assert out[0].type is EntityType.SOCIAL_PROFILE
    assert out[0].value == "https://github.com/rob"


def test_sherlock_parser_extracts_site_url_pairs():
    from weft.modules.username.sherlock import _parse_sherlock
    out = _parse_sherlock(
        "[*] Checking username rob on:\n"
        "[+] GitHub: https://github.com/rob\n"
        "[+] Twitter: https://twitter.com/rob\n"
        "[-] Missing: not shown\n"
    )
    assert out == [("GitHub", "https://github.com/rob"), ("Twitter", "https://twitter.com/rob")]


def test_registry_discovers_phase3_modules():
    from weft.core import registry
    registry.discover()
    names = set(registry.registered_classes())
    assert {"gravatar", "github_user", "github_email", "github_domain",
            "holehe", "maigret", "sherlock"} <= names
