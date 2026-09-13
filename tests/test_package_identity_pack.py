"""package_metadata (npm/PyPI maintainer identity) + StackExchange (mocked HTTP).

Shapes mirror the live responses from registry.npmjs.org, pypi.org, and api.stackexchange.com.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.software.package_metadata import PackageMetadata
from weft.modules.username.stackexchange import StackExchange

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _e(t, v):
    return Entity.make(t, v, source_module="seed", confidence=1.0, seed_id="s")


# --- npm metadata ------------------------------------------------------------

def test_package_metadata_npm_author_maintainers_links():
    http = FakeHttp({"registry.npmjs.org/express": (200, {
        "author": {"name": "TJ Holowaychuk", "email": "tj@vision-media.ca"},
        "maintainers": [{"name": "wesleytodd", "email": "wes@example.com"}],
        "homepage": "https://expressjs.com/",
        "repository": {"url": "git+https://github.com/expressjs/express.git"},
        "bugs": {"url": "https://github.com/expressjs/express/issues"}})})
    out = asyncio.run(PackageMetadata().run(_e(EntityType.PACKAGE, "npm:express"), _ctx(http)))
    persons = {e.value for e in out if e.type is EntityType.PERSON}
    emails = {e.value for e in out if e.type is EntityType.EMAIL}
    users = {e.value for e in out if e.type is EntityType.USERNAME}
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert "TJ Holowaychuk" in persons
    assert "tj@vision-media.ca" in emails and "wes@example.com" in emails
    assert "wesleytodd" in users
    assert "https://github.com/expressjs/express" in urls   # git+ / .git stripped


def test_package_metadata_pypi_author_email_and_project_urls():
    http = FakeHttp({"pypi.org/pypi/requests/json": (200, {"info": {
        "author": None, "author_email": "Kenneth Reitz <me@kennethreitz.org>", "home_page": None,
        "project_urls": {"Source": "https://github.com/psf/requests"}}})})
    out = asyncio.run(PackageMetadata().run(_e(EntityType.PACKAGE, "pypi:requests"), _ctx(http)))
    persons = {e.value for e in out if e.type is EntityType.PERSON}
    emails = {e.value for e in out if e.type is EntityType.EMAIL}
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert "Kenneth Reitz" in persons                       # parsed from "Name <email>"
    assert "me@kennethreitz.org" in emails
    assert "https://github.com/psf/requests" in urls


def test_package_metadata_unknown_ecosystem_returns_empty():
    assert asyncio.run(PackageMetadata().run(_e(EntityType.PACKAGE, "cargo:serde"), _ctx(FakeHttp({})))) == []


# --- StackExchange -----------------------------------------------------------

def test_stackexchange_emits_profiles_and_unescapes_name():
    http = FakeHttp({"api.stackexchange.com": (200, {"items": [
        {"display_name": "Jon Skeet", "reputation": 1529670, "user_id": 22656,
         "link": "https://stackoverflow.com/users/22656/jon-skeet"},
        {"display_name": "Jon Skeet&#39;s mentor", "reputation": 83, "user_id": 4338144,
         "link": "https://stackoverflow.com/users/4338144/x"}]})})
    out = asyncio.run(StackExchange().run(_e(EntityType.NAME, "Jon Skeet"), _ctx(http)))
    socials = [e for e in out if e.type is EntityType.SOCIAL_PROFILE]
    assert socials and socials[0].metadata["reputation"] == 1529670
    assert socials[1].metadata["display_name"] == "Jon Skeet's mentor"   # HTML-unescaped


def test_stackexchange_no_items_returns_empty():
    assert asyncio.run(StackExchange().run(_e(EntityType.USERNAME, "zzz"),
                                           _ctx(FakeHttp({"api.stackexchange.com": (200, {"items": []})})))) == []


def test_registry_discovers_package_identity_pack():
    from weft.core import registry
    registry.discover()
    assert {"package_metadata", "stackexchange"} <= set(registry.registered_classes())
