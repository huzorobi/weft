"""Injectable secrets provider (env, file, chained) — vault-ready."""
from __future__ import annotations

import os

from weft.core.secrets import (
    ChainedSecrets, EnvSecrets, FileSecrets, MappingSecrets, default_secrets,
)


def test_env_secrets(monkeypatch):
    monkeypatch.setenv("WEFT_TEST_KEY", "v1")
    assert EnvSecrets().get("WEFT_TEST_KEY") == "v1"
    assert EnvSecrets().get("WEFT_MISSING_XYZ") is None


def test_mapping_empty_is_none():
    m = MappingSecrets({"A": "1", "B": ""})
    assert m.get("A") == "1"
    assert m.get("B") is None       # empty treated as absent
    assert m.get("C") is None


def test_file_secrets_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"GITHUB_TOKEN": "abc", "HIBP_API_KEY": "def"}')
    fs = FileSecrets(p)
    assert fs.get("GITHUB_TOKEN") == "abc"
    assert fs.get("HIBP_API_KEY") == "def"


def test_file_secrets_env_style(tmp_path):
    p = tmp_path / "s.env"
    p.write_text('# comment\nGITHUB_TOKEN="abc"\nCOMPANIES_HOUSE_API_KEY=xyz\n')
    fs = FileSecrets(p)
    assert fs.get("GITHUB_TOKEN") == "abc"
    assert fs.get("COMPANIES_HOUSE_API_KEY") == "xyz"


def test_file_secrets_missing_file(tmp_path):
    assert FileSecrets(tmp_path / "nope.json").get("X") is None


def test_chained_first_non_empty_wins():
    a = MappingSecrets({"K": "from_a"})
    b = MappingSecrets({"K": "from_b", "ONLY_B": "b"})
    c = ChainedSecrets(a, b)
    assert c.get("K") == "from_a"
    assert c.get("ONLY_B") == "b"
    assert c.get("MISSING") is None


def test_default_secrets_env_then_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ONLY_FILE", raising=False)
    p = tmp_path / "s.json"
    p.write_text('{"ONLY_FILE": "f"}')
    prov = default_secrets(str(p))
    assert prov.get("ONLY_FILE") == "f"        # falls through env to file
