"""Entity normalisation and dedup-key behaviour."""
from __future__ import annotations

import pytest

from weft.core.entity import Entity, EntityType, normalise_value


def _e(etype, value):
    return Entity.make(etype, value, source_module="t", confidence=0.9, seed_id="s1")


def test_email_is_lowercased():
    assert _e(EntityType.EMAIL, "Rob@Example.COM").value == "rob@example.com"


def test_username_strips_at_sign():
    assert _e(EntityType.USERNAME, "@huzo").value == "huzo"


def test_domain_lowercased_and_trailing_slash_removed():
    assert _e(EntityType.DOMAIN, "Example.COM/").value == "example.com"


def test_name_whitespace_collapsed():
    assert _e(EntityType.NAME, "  Robert   Huzo  ").value == "Robert Huzo"


def test_phone_national_and_international_collapse_to_one_key():
    a = _e(EntityType.PHONE, "0161 123 4567")
    b = _e(EntityType.PHONE, "+44 161 123 4567")
    assert a.key() == b.key(), (a.value, b.value)


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValueError):
        Entity(type=EntityType.EMAIL, value="x@y.com", source_module="t", confidence=1.5, seed_id="s")


def test_key_is_type_scoped():
    assert _e(EntityType.EMAIL, "a@b.com").key() == "email:a@b.com"
    assert _e(EntityType.USERNAME, "abc").key() == "username:abc"
