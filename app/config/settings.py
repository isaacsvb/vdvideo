"""Application configuration.

Settings are loaded with this precedence (highest wins):
  1. Environment variables  (e.g. OPENAI_API_KEY, PEXELS_API_KEY)
  2. config.toml in the project root
  3. Built-in defaults

Secrets are never hardcoded; they come from config.toml (gitignored) or env vars.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import toml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.toml"


class OpenAIConfig(BaseModel):
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = ""


class GeminiConfig(BaseModel):
    api_key: str = ""
    # "gemini-flash-latest" is an alias that tracks the current stable Flash
    # model, so it won't break when a specific version is retired.
    model: str = "gemini-flash-latest"


class LLMConfig(BaseModel):
    provider: str = "openai"
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)


class PexelsConfig(BaseModel):
    api_key: str = ""


class PixabayConfig(BaseModel):
    api_key: str = ""


class MaterialConfig(BaseModel):
    provider: str = "pexels"
    pexels: PexelsConfig = Field(default_factory=PexelsConfig)
    pixabay: PixabayConfig = Field(default_factory=PixabayConfig)


class TTSConfig(BaseModel):
    provider: str = "edge"
    default_voice: str = "en-US-AvaNeural"


class YouTubeConfig(BaseModel):
    # Path to the OAuth client-secrets JSON downloaded from Google Cloud Console
    # (Desktop app credentials with the YouTube Data API v3 enabled).
    client_secrets_file: str = ""
    # Where the cached OAuth token is stored after the first authorization.
    token_file: str = "youtube_token.json"
    # Default upload settings.
    privacy_status: str = "private"  # private | unlisted | public
    category_id: str = "22"          # 22 = People & Blogs


class AppConfig(BaseModel):
    storage_dir: str = "storage"
    keep_intermediate: bool = False


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    material: MaterialConfig = Field(default_factory=MaterialConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)

    @property
    def storage_path(self) -> Path:
        p = PROJECT_ROOT / self.app.storage_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


def _load_toml() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return toml.load(CONFIG_PATH)
    return {}


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Overlay environment variables onto the loaded config dict."""
    data.setdefault("llm", {}).setdefault("openai", {})
    data["llm"].setdefault("gemini", {})
    data.setdefault("material", {}).setdefault("pexels", {})
    data["material"].setdefault("pixabay", {})

    env_map = {
        ("llm", "openai", "api_key"): "OPENAI_API_KEY",
        ("llm", "openai", "base_url"): "OPENAI_BASE_URL",
        ("llm", "gemini", "api_key"): "GEMINI_API_KEY",
        ("material", "pexels", "api_key"): "PEXELS_API_KEY",
        ("material", "pixabay", "api_key"): "PIXABAY_API_KEY",
        ("youtube", "client_secrets_file"): "YOUTUBE_CLIENT_SECRETS_FILE",
    }
    data.setdefault("youtube", {})
    for path, env_name in env_map.items():
        val = os.getenv(env_name)
        if val:
            node = data
            for key in path[:-1]:
                node = node.setdefault(key, {})
            if not node.get(path[-1]):
                node[path[-1]] = val

    # Allow overriding the active providers from env too.
    if os.getenv("LLM_PROVIDER"):
        data.setdefault("llm", {})["provider"] = os.environ["LLM_PROVIDER"]
    if os.getenv("MATERIAL_PROVIDER"):
        data.setdefault("material", {})["provider"] = os.environ["MATERIAL_PROVIDER"]
    return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data = _apply_env_overrides(_load_toml())
    return Settings(**data)


def reload_settings() -> Settings:
    """Clear the cache and reload (useful after the UI writes config)."""
    get_settings.cache_clear()
    return get_settings()
