"""Maintainer identity from a software package's registry metadata (free, keyless, passive).

A published package names the people behind it. For a PACKAGE entity (e.g. ``npm:express`` or
``pypi:requests``) this reads the registry metadata and emits the author's name and email, the
maintainer handles, and the homepage/repository links — turning a package into identity pivots.
Keyless, passive. Currently covers npm and PyPI.
"""
from __future__ import annotations

import re

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

NPM = "https://registry.npmjs.org/"
PYPI = "https://pypi.org/pypi/{name}/json"
_NAME_EMAIL = re.compile(r"^(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$")


@register
class PackageMetadata(Module):
    name = "package_metadata"
    accepts = [EntityType.PACKAGE]
    produces = [EntityType.PERSON, EntityType.EMAIL, EntityType.URL, EntityType.USERNAME]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 25

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        ecosystem, _, name = entity.value.partition(":")
        if not name:
            return []
        eco = ecosystem.lower()
        if eco == "npm":
            status, data = await ctx.http.get_json(f"{NPM}{name}")
            return _parse_npm(data, entity, self.name, self.reliability) if status == 200 and isinstance(data, dict) else []
        if eco == "pypi":
            status, data = await ctx.http.get_json(PYPI.format(name=name))
            return _parse_pypi(data, entity, self.name, self.reliability) if status == 200 and isinstance(data, dict) else []
        return []


def _split_name_email(raw: str) -> tuple[str, str]:
    m = _NAME_EMAIL.match(raw.strip())
    if m:
        return m.group("name").strip(), m.group("email").strip()
    return (raw.strip(), "") if "@" not in raw else ("", raw.strip())


def _clean_repo(url: str) -> str:
    return re.sub(r"^git\+", "", url).removesuffix(".git")


def _emit_person_email(name: str, email: str, seed, source, reliability, role) -> list[Entity]:
    out = []
    if name and "@" not in name:
        out.append(Entity.make(EntityType.PERSON, name, source_module=source, confidence=reliability,
                               seed_id=seed.seed_id, metadata={"role": role, "package": seed.value}))
    if email and "@" in email:
        out.append(Entity.make(EntityType.EMAIL, email, source_module=source, confidence=reliability,
                               seed_id=seed.seed_id, metadata={"role": role, "package": seed.value}))
    return out


def _parse_npm(data: dict, seed, source, reliability) -> list[Entity]:
    out: list[Entity] = []
    author = data.get("author")
    if isinstance(author, dict):
        out += _emit_person_email(author.get("name", ""), author.get("email", ""), seed, source, reliability, "author")
    elif isinstance(author, str):
        n, e = _split_name_email(author)
        out += _emit_person_email(n, e, seed, source, reliability, "author")
    for m in (data.get("maintainers") or []):
        if isinstance(m, dict):
            if m.get("name"):
                out.append(Entity.make(EntityType.USERNAME, m["name"], source_module=source,
                                       confidence=reliability, seed_id=seed.seed_id,
                                       metadata={"platform": "npm", "role": "maintainer", "package": seed.value}))
            if m.get("email") and "@" in m["email"]:
                out.append(Entity.make(EntityType.EMAIL, m["email"], source_module=source, confidence=reliability,
                                       seed_id=seed.seed_id, metadata={"role": "maintainer", "package": seed.value}))
    for url in (data.get("homepage"), (data.get("repository") or {}).get("url"), (data.get("bugs") or {}).get("url")):
        if url and isinstance(url, str) and url.startswith(("http", "git")):
            out.append(Entity.make(EntityType.URL, _clean_repo(url), source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata={"role": "package link", "package": seed.value}))
    return out


def _parse_pypi(data: dict, seed, source, reliability) -> list[Entity]:
    info = data.get("info", {}) or {}
    out: list[Entity] = []
    if info.get("author"):
        out += _emit_person_email(info["author"], info.get("author_email", ""), seed, source, reliability, "author")
    if info.get("author_email"):
        n, e = _split_name_email(info["author_email"])
        out += _emit_person_email(n, e, seed, source, reliability, "author")
    links = [info.get("home_page")] + list((info.get("project_urls") or {}).values())
    for url in links:
        if url and isinstance(url, str) and url.startswith("http"):
            out.append(Entity.make(EntityType.URL, _clean_repo(url), source_module=source, confidence=reliability,
                                   seed_id=seed.seed_id, metadata={"role": "package link", "package": seed.value}))
    return out
