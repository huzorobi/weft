"""The entity model and normalisation.

An :class:`Entity` is one node in the recon graph. Every entity is normalised
*before* anything touches it, so that the same real-world thing arriving from two
sources collapses to one node. The dedup key is derived from the normalised value:
``+441611234567`` and ``0161 123 4567`` must become the same ``PHONE`` node.

Normalisation is deliberately dependency-light. Phone numbers use Google's
``phonenumbers`` (libphonenumber) when it is installed; if it is not, we fall back
to a conservative digit/`+` normalisation so the core stays importable and testable
without the full runtime stack.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

try:  # optional at import time; required for accurate E.164 in the running app
    import phonenumbers  # type: ignore

    _HAVE_PHONENUMBERS = True
except Exception:  # pragma: no cover - exercised only where the dep is absent
    _HAVE_PHONENUMBERS = False


class EntityType(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    USERNAME = "username"
    NAME = "name"
    PERSON = "person"
    DOMAIN = "domain"
    ORGANISATION = "organisation"
    ADDRESS = "address"
    URL = "url"
    SOCIAL_PROFILE = "social_profile"
    IP = "ip"
    IMAGE = "image"
    ARCHIVE_SNAPSHOT = "archive_snapshot"
    BREACH = "breach"
    CRYPTO_ADDRESS = "crypto_address"
    CVE = "cve"


_WS = re.compile(r"\s+")


def normalise_value(entity_type: EntityType, raw: str, *, default_region: str = "GB") -> str:
    """Return the canonical form of ``raw`` for ``entity_type``.

    Never raises on malformed input; it returns a best-effort canonical string so
    that dedup stays deterministic. Validation (is this a *real* number?) is a
    separate concern handled by the modules, not by normalisation.
    """
    value = (raw or "").strip()
    if not value:
        return ""

    if entity_type == EntityType.PHONE:
        return _normalise_phone(value, default_region)
    if entity_type == EntityType.EMAIL:
        return value.lower()
    if entity_type in (EntityType.DOMAIN, EntityType.URL):
        return value.lower().rstrip("/")
    if entity_type == EntityType.USERNAME:
        return value.lstrip("@").strip()
    if entity_type in (EntityType.NAME, EntityType.PERSON, EntityType.ORGANISATION, EntityType.ADDRESS):
        return _WS.sub(" ", value).strip()
    if entity_type == EntityType.CVE:
        return value.upper()
    if entity_type == EntityType.CRYPTO_ADDRESS:
        # Ethereum (0x + 40 hex) is case-insensitive (EIP-55 checksum is only a hint) — lowercase
        # so 0xABC…==0xabc… dedupe. Bitcoin base58/bech32 IS case-sensitive — trim only, never fold.
        if len(value) == 42 and value[:2].lower() == "0x":
            return value.lower()
        return value.lstrip().rstrip()
    # IP, IMAGE, ARCHIVE_SNAPSHOT, SOCIAL_PROFILE, BREACH: trim only.
    return value


def _normalise_phone(value: str, default_region: str) -> str:
    if _HAVE_PHONENUMBERS:
        try:
            parsed = phonenumbers.parse(value, None if value.startswith("+") else default_region)
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass  # fall through to conservative normalisation
    digits = re.sub(r"[^\d+]", "", value)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    return digits


@dataclass
class Entity:
    """One node in the recon graph.

    ``value`` is always the normalised canonical form. Use :meth:`make` to build
    an entity from raw input so normalisation is never skipped.
    """

    type: EntityType
    value: str
    source_module: str
    confidence: float  # 0.0-1.0
    seed_id: str
    metadata: dict = field(default_factory=dict)
    label: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence!r}")

    @classmethod
    def make(
        cls,
        entity_type: EntityType,
        raw_value: str,
        *,
        source_module: str,
        confidence: float,
        seed_id: str,
        metadata: dict | None = None,
        label: str | None = None,
        default_region: str = "GB",
    ) -> "Entity":
        """Build an entity, normalising ``raw_value`` first."""
        return cls(
            type=entity_type,
            value=normalise_value(entity_type, raw_value, default_region=default_region),
            source_module=source_module,
            confidence=confidence,
            seed_id=seed_id,
            metadata=dict(metadata or {}),
            label=label,
        )

    def key(self) -> str:
        """Stable dedup key off the normalised value (case-insensitive)."""
        return f"{self.type.value}:{self.value.lower().strip()}"
