"""Runtime configuration.

Only free keys ever appear here. A module whose free key is missing disables itself
cleanly and says so in the run summary; it never crashes the run. Settings are read
from the environment / ``.env`` via Pydantic Settings, and secret access goes through
an injectable provider so we can move to a vault later without touching modules.

Pydantic is optional at import time: if it is not installed (for example when running
the pure compliance unit tests) a lightweight environment-backed fallback is used so
the package stays importable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

        # Graph store (Neo4j).
        neo4j_uri: str = "bolt://localhost:7687"
        neo4j_user: str = "neo4j"
        neo4j_password: str = "change_me"

        # Metadata + audit store.
        database_url: str = "sqlite:///weft-dev.db"

        # Self-hosted search.
        searxng_url: str = "http://localhost:8080"

        # Free keys (never paid). Empty means the module self-disables.
        companies_house_api_key: str | None = None
        github_token: str | None = None
        opencorporates_api_key: str | None = None
        hibp_api_key: str | None = None

        # Orchestrator defaults.
        depth_default: int = 2

        # Local reasoner (optional, local-only). Small model for an 8GB GPU.
        ollama_url: str = "http://localhost:11434"
        reasoner_model: str = "llama3.2:3b"

        # Optional on-disk secrets file (chained after the environment). Vault slots in here.
        secrets_file: str | None = None

    def load_settings() -> "Settings":
        return Settings()

except Exception:  # pragma: no cover - fallback when pydantic-settings is absent
    @dataclass
    class Settings:  # type: ignore[no-redef]
        neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password: str = os.getenv("NEO4J_PASSWORD", "change_me")
        database_url: str = os.getenv("DATABASE_URL", "sqlite:///weft-dev.db")
        searxng_url: str = os.getenv("SEARXNG_URL", "http://localhost:8080")
        companies_house_api_key: str | None = os.getenv("COMPANIES_HOUSE_API_KEY")
        github_token: str | None = os.getenv("GITHUB_TOKEN")
        opencorporates_api_key: str | None = os.getenv("OPENCORPORATES_API_KEY")
        hibp_api_key: str | None = os.getenv("HIBP_API_KEY")
        depth_default: int = int(os.getenv("DEPTH_DEFAULT", "2"))
        ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
        reasoner_model: str = os.getenv("REASONER_MODEL", "llama3.2:3b")
        secrets_file: str | None = os.getenv("SECRETS_FILE")

    def load_settings() -> "Settings":
        return Settings()


class EnvSecrets:
    """A SecretsAccessor backed by the environment. Injected into RunContext."""

    def get(self, name: str) -> str | None:
        return os.getenv(name)
