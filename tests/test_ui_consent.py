"""One-time terms acceptance."""
from __future__ import annotations

import os

from weft.ui import consent


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("WEFT_HOME", str(tmp_path))


def test_not_accepted_by_default(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert consent.is_accepted() is False
    assert consent.accepted_record() is None


def test_record_then_accepted(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    rec = consent.record_acceptance("Rob Huzo")
    assert rec["operator"] == "Rob Huzo" and rec["version"] == consent.TERMS_VERSION
    assert consent.is_accepted() is True
    assert consent.accepted_record()["operator"] == "Rob Huzo"


def test_version_bump_invalidates_acceptance(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    consent.record_acceptance("x")
    assert consent.is_accepted("some-newer-version") is False   # re-consent required on new terms


def test_terms_cover_uk_eu_us(tmp_path, monkeypatch):
    t = consent.TERMS_TEXT
    assert "UK GDPR" in t and "General Data Protection Regulation" in t
    assert "Computer Fraud and Abuse Act" in t
    assert "passive" in t.lower()
