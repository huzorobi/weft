"""IP reputation via public threat blocklists (free, keyless, passive).

Checks an IP against several well-maintained, keyless, commercial-clean blocklists and reports
which ones list it. The more lists an IP appears on, the stronger the signal. Each list is a
bulk file, downloaded and cached once per run; membership then runs locally. Passive — reads
published lists, never contacts the IP.
"""
from __future__ import annotations

import asyncio
import ipaddress

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, HealthStatus, Module
from weft.core.registry import register

# (name, url, kind): "ip" = one address per line, "cidr" = network per line.
LISTS = [
    ("ipsum_l3", "https://raw.githubusercontent.com/stamparm/ipsum/master/levels/3.txt", "ip"),
    ("blocklist_de", "https://lists.blocklist.de/lists/all.txt", "ip"),
    ("cins_army", "https://cinsscore.com/list/ci-badguys.txt", "ip"),
    ("greensnow", "https://blocklist.greensnow.co/greensnow.txt", "ip"),
    ("spamhaus_drop", "https://www.spamhaus.org/drop/drop.txt", "cidr"),
]


def parse_ip_list(text: str) -> set[str]:
    out: set[str] = set()
    for line in text.splitlines():
        tok = line.strip().split()[0] if line.strip() else ""
        if not tok or tok[0] in "#;":
            continue
        try:
            out.add(str(ipaddress.ip_address(tok)))
        except ValueError:
            continue
    return out


def parse_cidr_list(text: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    for line in text.splitlines():
        tok = line.strip().split()[0] if line.strip() else ""
        if not tok or tok[0] in "#;":
            continue
        try:
            out.append(ipaddress.ip_network(tok, strict=False))
        except ValueError:
            continue
    return out


@register
class IpBlocklists(Module):
    name = "ip_blocklists"
    accepts = [EntityType.IP]
    produces = [EntityType.IP]
    access = Access.FREE_API
    reliability = 0.75
    timeout_s = 60

    def __init__(self) -> None:
        self._ips: dict[str, set[str]] | None = None
        self._cidrs: dict[str, list] | None = None
        self._lock: asyncio.Lock | None = None

    async def health(self, ctx=None):
        if ctx is None or ctx.http is None:
            return HealthStatus.down("no http client in context")
        return HealthStatus.up()

    async def _load(self, ctx) -> None:
        if self._ips is not None:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._ips is not None:
                return
            ips: dict[str, set[str]] = {}
            cidrs: dict[str, list] = {}
            for name, url, kind in LISTS:
                status, text = await ctx.http.get_text(url)
                if status != 200 or not text:
                    continue
                if kind == "ip":
                    ips[name] = parse_ip_list(text)
                else:
                    cidrs[name] = parse_cidr_list(text)
            self._ips, self._cidrs = ips, cidrs

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if ctx.http is None:
            return []
        try:
            addr = ipaddress.ip_address(entity.value)
        except ValueError:
            return []
        await self._load(ctx)
        hits = self._match(entity.value, addr)
        if not hits:
            return []
        conf = min(self.reliability + 0.05 * (len(hits) - 1), 0.95)
        return [Entity(
            type=EntityType.IP, value=entity.value, source_module=self.name,
            confidence=conf, seed_id=entity.seed_id,
            metadata={"reputation": "listed", "on_blocklists": hits, "list_count": len(hits)},
            label=f"listed on {len(hits)} blocklist(s)",
        )]

    def _match(self, value: str, addr) -> list[str]:
        hits: list[str] = []
        for name, ipset in (self._ips or {}).items():
            if value in ipset:
                hits.append(name)
        for name, nets in (self._cidrs or {}).items():
            if any(addr in n for n in nets):
                hits.append(name)
        return hits
