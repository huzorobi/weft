"""IP abuse reputation via AbuseIPDB (free key, passive).

Returns AbuseIPDB's crowd-sourced abuse confidence for an IP — a 0-100 score, report count,
and the network it belongs to. Free tier is 1,000 checks/day. Self-disables without a key.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.keyed import KeyedApiModule
from weft.core.registry import register

CHECK = "https://api.abuseipdb.com/api/v2/check"


@register
class AbuseIpdb(KeyedApiModule):
    name = "abuseipdb"
    accepts = [EntityType.IP]
    produces = [EntityType.IP]
    secret_env = "ABUSEIPDB_API_KEY"
    reliability = 0.75
    timeout_s = 25

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        headers = self._key_header(ctx, "Key")
        if ctx.http is None or headers is None:
            return []
        headers["Accept"] = "application/json"
        status, data = await ctx.http.get_json(
            CHECK, params={"ipAddress": entity.value, "maxAgeInDays": "90"}, headers=headers)
        if status != 200 or not isinstance(data, dict):
            return []
        d = data.get("data", {}) or {}
        score = d.get("abuseConfidenceScore")
        if score is None:
            return []
        return [Entity(
            type=EntityType.IP, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id,
            metadata={k: v for k, v in {
                "abuse_confidence": score, "total_reports": d.get("totalReports"),
                "country": d.get("countryCode"), "isp": d.get("isp"),
                "usage_type": d.get("usageType"), "domain": d.get("domain"),
                "is_tor": d.get("isTor"),
            }.items() if v is not None},
            label=f"abuse score {score}")]
