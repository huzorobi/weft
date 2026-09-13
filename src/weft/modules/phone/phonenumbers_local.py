"""Offline phone enrichment via Google libphonenumber.

Replaces every paid carrier-lookup API for the free build: region, line type,
validity and timezones, all offline and instant. It enriches the phone node in place
(returns the same entity key with metadata) rather than spawning new nodes.

Honesty note recorded in the metadata: ``carrier`` is the *original* number-block
allocation. UK number portability means the current carrier is frequently different,
so the value is flagged ``carrier_note = "original allocation; may be ported"``.
"""
from __future__ import annotations

from weft.core.entity import Entity, EntityType
from weft.core.module import Access, Module
from weft.core.registry import register

try:
    import phonenumbers
    from phonenumbers import carrier, geocoder, timezone
    from phonenumbers import PhoneNumberType, number_type

    _HAVE = True
except Exception:  # pragma: no cover
    _HAVE = False

_LINE_TYPES = {}
if _HAVE:
    _LINE_TYPES = {
        PhoneNumberType.MOBILE: "mobile",
        PhoneNumberType.FIXED_LINE: "fixed_line",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
        PhoneNumberType.VOIP: "voip",
        PhoneNumberType.TOLL_FREE: "toll_free",
        PhoneNumberType.PREMIUM_RATE: "premium_rate",
    }


@register
class PhoneNumbersLocal(Module):
    name = "phonenumbers_local"
    accepts = [EntityType.PHONE]
    produces = [EntityType.PHONE]
    access = Access.OFFLINE
    reliability = 0.85

    async def health(self, ctx=None):
        from weft.core.module import HealthStatus
        return HealthStatus.up() if _HAVE else HealthStatus.down("phonenumbers not installed")

    async def run(self, entity: Entity, ctx) -> list[Entity]:
        if not _HAVE:
            return []
        try:
            num = phonenumbers.parse(entity.value, None)
        except Exception:
            return []
        if not phonenumbers.is_possible_number(num):
            return []

        lt = _LINE_TYPES.get(number_type(num), "unknown")
        meta = {
            "region": geocoder.description_for_number(num, "en") or None,
            "region_code": phonenumbers.region_code_for_number(num),
            "carrier": carrier.name_for_number(num, "en") or None,
            "carrier_note": "original allocation; may be ported",
            "line_type": lt,
            "valid": phonenumbers.is_valid_number(num),
            "timezones": list(timezone.time_zones_for_number(num)),
        }
        meta = {k: v for k, v in meta.items() if v not in (None, [], "")}
        # Enrich the phone node in place (same key -> merged metadata).
        return [Entity(
            type=EntityType.PHONE, value=entity.value, source_module=self.name,
            confidence=self.reliability, seed_id=entity.seed_id, metadata=meta,
            label=meta.get("region"),
        )]
