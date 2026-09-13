"""Secret access behind an injectable provider, so a vault can slot in later.

Modules never read the environment directly; they ask the injected provider. The
default chains the process environment over an optional on-disk secrets file, and a
vault-backed provider can be added without touching a single module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretsProvider(Protocol):
    def get(self, name: str) -> str | None: ...


class EnvSecrets:
    """Reads from the process environment."""

    def get(self, name: str) -> str | None:
        return os.getenv(name)


class MappingSecrets:
    """Reads from an in-memory mapping (tests, or a file-loaded set)."""

    def __init__(self, mapping: dict[str, str] | None = None):
        self._m = dict(mapping or {})

    def get(self, name: str) -> str | None:
        v = self._m.get(name)
        return v if v else None


class FileSecrets(MappingSecrets):
    """Reads a JSON object or a ``KEY=value`` file into a mapping. Missing file is empty."""

    def __init__(self, path: str | os.PathLike):
        super().__init__(_load_file(Path(path)))


class ChainedSecrets:
    """Tries each provider in order; first non-empty value wins."""

    def __init__(self, *providers: SecretsProvider):
        self._providers = [p for p in providers if p is not None]

    def get(self, name: str) -> str | None:
        for p in self._providers:
            v = p.get(name)
            if v:
                return v
        return None


def _load_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def default_secrets(secrets_file: str | None = None) -> SecretsProvider:
    """Environment first, then an optional on-disk secrets file. Vault provider slots in here."""
    providers: list[SecretsProvider] = [EnvSecrets()]
    if secrets_file:
        providers.append(FileSecrets(secrets_file))
    return ChainedSecrets(*providers)
