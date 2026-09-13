"""Hacker News + npm developer footprint (mocked HTTP).

Shapes mirror the live responses verified against hacker-news.firebaseio.com and
registry.npmjs.org before shipping.
"""
from __future__ import annotations

import asyncio

from weft.core.entity import Entity, EntityType
from weft.core.module import RunContext
from weft.modules.username.hackernews import HackerNews
from weft.modules.username.npm import Npm

from _fakes import FakeHttp


def _ctx(http):
    return RunContext(engagement_id="e", operator="rob", allow_tos_risk=False, depth=0, http=http)


def _user(v="sindresorhus"):
    return Entity.make(EntityType.USERNAME, v, source_module="seed", confidence=1.0, seed_id="s")


# --- Hacker News -------------------------------------------------------------

def test_hackernews_profile_and_about_links():
    http = FakeHttp({"v0/user/pg.json": (200, {
        "id": "pg", "karma": 157316, "created": 1160418092, "submitted": [1, 2, 3],
        "about": 'Founder. <a href="https://paulgraham.com">site</a> also http://ycombinator.com'})})
    out = asyncio.run(HackerNews().run(_user("pg"), _ctx(http)))
    socials = [e for e in out if e.type is EntityType.SOCIAL_PROFILE]
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert socials and socials[0].value == "https://news.ycombinator.com/user?id=pg"
    assert socials[0].metadata["karma"] == 157316
    assert "https://paulgraham.com" in urls
    assert "http://ycombinator.com" in urls


def test_hackernews_unknown_user_returns_empty():
    assert asyncio.run(HackerNews().run(_user("nobody"),
                                        _ctx(FakeHttp({"v0/user/nobody.json": (200, None)})))) == []


# --- npm ---------------------------------------------------------------------

def test_npm_keeps_owned_packages_and_repo_links():
    http = FakeHttp({"registry.npmjs.org/-/v1/search": (200, {"objects": [
        {"package": {"name": "chalk", "description": "Terminal string styling",
                     "publisher": {"username": "sindresorhus"},
                     "links": {"npm": "https://www.npmjs.com/package/chalk",
                               "repository": "https://github.com/chalk/chalk"}}},
        {"package": {"name": "someone-else-pkg", "publisher": {"username": "otheruser"},
                     "links": {"npm": "https://www.npmjs.com/package/someone-else-pkg"}}},  # not owned -> dropped
    ]})})
    out = asyncio.run(Npm().run(_user("sindresorhus"), _ctx(http)))
    urls = {e.value for e in out if e.type is EntityType.URL}
    assert "https://www.npmjs.com/package/chalk" in urls
    assert "https://github.com/chalk/chalk" in urls          # repo pivot
    assert not any("someone-else-pkg" in u for u in urls)    # foreign package filtered


def test_npm_matches_via_maintainer():
    http = FakeHttp({"registry.npmjs.org/-/v1/search": (200, {"objects": [
        {"package": {"name": "p", "maintainers": [{"username": "sindresorhus"}],
                     "publisher": {"username": "bot"}, "links": {"npm": "https://www.npmjs.com/package/p"}}},
    ]})})
    out = asyncio.run(Npm().run(_user("sindresorhus"), _ctx(http)))
    assert any(e.value == "https://www.npmjs.com/package/p" for e in out)


def test_npm_no_objects_returns_empty():
    assert asyncio.run(Npm().run(_user(), _ctx(FakeHttp({"registry.npmjs.org/-/v1/search": (200, {"objects": []})})))) == []


def test_registry_discovers_dev_footprint():
    from weft.core import registry
    registry.discover()
    assert {"hackernews", "npm"} <= set(registry.registered_classes())
