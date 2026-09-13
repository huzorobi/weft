"""Test doubles: a fake HTTP client, fake secrets, and simple fake modules."""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module


class FakeHttp:
    """Returns canned (status, payload) based on the first matching URL substring."""

    def __init__(self, routes: dict[str, tuple[int, object]]):
        self._routes = routes
        self.calls: list[str] = []

    def _match(self, url):
        self.calls.append(url)
        for frag, resp in self._routes.items():
            if frag in url:
                return resp
        return (404, None)

    async def get_json(self, url, *, params=None, headers=None, auth=None):
        # include params in the match target so appointment vs search can differ
        target = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        return self._match(target)

    async def get_text(self, url, *, params=None, headers=None):
        status, data = self._match(url)
        return status, (data if isinstance(data, str) else "")


class FakeSecrets:
    def __init__(self, mapping: dict[str, str]):
        self._m = mapping

    def get(self, name):
        return self._m.get(name)


class StaticModule(Module):
    """A module that returns a fixed list of children for a given entity type."""

    def __init__(self, name, accepts, children):
        self.name = name
        self.accepts = accepts
        self.produces = [c.type for c in children]
        self.access = Access.OFFLINE
        self._children = children

    async def run(self, entity, ctx):
        return list(self._children)


class BoomModule(Module):
    name = "boom"
    accepts = [EntityType.DOMAIN]
    produces = []
    access = Access.OFFLINE

    async def run(self, entity, ctx):
        raise RuntimeError("kaboom")


class DownModule(Module):
    name = "down"
    accepts = [EntityType.DOMAIN]
    produces = []
    access = Access.OFFLINE

    async def health(self, ctx=None):
        return HealthStatus.down("intentionally down")

    async def run(self, entity, ctx):
        raise AssertionError("run() must not be called when health is down")
