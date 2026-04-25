from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_yaml() -> dict[str, Any]:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Optional env overrides ────────────────────────────────────────
    # Ollama runs locally — no API key needed.
    ollama_host: str = "http://localhost:11434"
    # TMDB: free with email registration at themoviedb.org (no credit card).
    # Leave blank to use DuckDuckGo-based movie search as fallback.
    tmdb_api_key: str = ""
    # ElevenLabs: get a free key at elevenlabs.io (10k chars/month free tier).
    elevenlabs_api_key: str = ""
    # Brave Search API: get a free key at brave.com/search/api (2k queries/month).
    # When set, Brave is used as the primary search engine (fast & reliable).
    # DuckDuckGo is used as fallback when this is blank.
    brave_search_api_key: str = ""

    # Social OAuth — optional, see .env.example for setup instructions
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    # PostgreSQL connection string (production / Docker).
    # Format: postgresql+psycopg2://user:password@host:5432/gaaia
    # When set, MemoryStore uses PostgreSQL with `auth` and `data` schemas.
    # When blank, SQLite is used (local dev default — no setup required).
    database_url: str = ""

    # ── YAML config (loaded separately, attached at construction) ─────
    _yaml: dict[str, Any] = {}
    # Populated at server startup by the model router — overrides YAML model keys
    # for any models that don't fit in system RAM or aren't installed.
    _effective_model_overrides: dict[str, Any] = {}

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "_yaml", _load_yaml())
        object.__setattr__(self, "_effective_model_overrides", {})

    # ── Convenience accessors ─────────────────────────────────────────

    @property
    def app(self) -> dict[str, Any]:
        return self._yaml.get("app", {})

    @property
    def model(self) -> dict[str, Any]:
        """Merge YAML model config with runtime overrides from the model router."""
        base = dict(self._yaml.get("model", {}))
        base.update(self._effective_model_overrides)
        return base

    def apply_model_routing(self, overrides: dict[str, Any]) -> None:
        """Called once at startup with the RAM-constrained model overrides."""
        object.__setattr__(self, "_effective_model_overrides", dict(overrides))

    @property
    def personality(self) -> dict[str, Any]:
        return self._yaml.get("personality", {})

    @property
    def voice(self) -> dict[str, Any]:
        return self._yaml.get("voice", {})

    @property
    def memory(self) -> dict[str, Any]:
        return self._yaml.get("memory", {})

    @property
    def response_cache(self) -> dict[str, Any]:
        return self._yaml.get("response_cache", {})

    @property
    def approval(self) -> dict[str, Any]:
        return self._yaml.get("approval", {})

    @property
    def server(self) -> dict[str, Any]:
        return self._yaml.get("server", {})

    @property
    def ui(self) -> dict[str, Any]:
        return self._yaml.get("ui", {})

    @property
    def research(self) -> dict[str, Any]:
        return self._yaml.get("research", {})

    @property
    def dev(self) -> dict[str, Any]:
        return self._yaml.get("dev", {})

    @property
    def camera(self) -> dict[str, Any]:
        return self._yaml.get("camera", {})

    @property
    def knowledge_feed(self) -> dict[str, Any]:
        return self._yaml.get("knowledge_feed", {})

    @property
    def data_dir(self) -> Path:
        raw = self.app.get("data_dir", "~/GAAIA")
        return Path(os.path.expanduser(raw))

    @property
    def db_path(self) -> Path:
        filename = self.memory.get("db_filename", "gaaia.db")
        return self.data_dir / filename

    @property
    def notes_dir(self) -> Path:
        return self.data_dir / "notes"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
