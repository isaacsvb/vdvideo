"""Tests for settings loading and env-var override precedence."""
from __future__ import annotations

import app.config.settings as settings_mod
from app.config.settings import Settings, _apply_env_overrides


class TestEnvOverrides:
    def test_env_fills_missing_keys(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        monkeypatch.setenv("PEXELS_API_KEY", "pexels-from-env")
        data = _apply_env_overrides({})
        assert data["llm"]["openai"]["api_key"] == "sk-from-env"
        assert data["material"]["pexels"]["api_key"] == "pexels-from-env"

    def test_toml_value_wins_when_present(self, monkeypatch):
        # Existing (toml) value should NOT be clobbered by env.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        data = _apply_env_overrides({"llm": {"openai": {"api_key": "sk-from-toml"}}})
        assert data["llm"]["openai"]["api_key"] == "sk-from-toml"

    def test_provider_override_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("MATERIAL_PROVIDER", "pixabay")
        data = _apply_env_overrides({})
        assert data["llm"]["provider"] == "gemini"
        assert data["material"]["provider"] == "pixabay"


class TestSettingsDefaults:
    def test_defaults(self):
        s = Settings()
        assert s.llm.provider == "openai"
        assert s.material.provider == "pexels"
        assert s.tts.provider == "edge"
        assert s.app.storage_dir == "storage"

    def test_storage_path_created(self, tmp_path, monkeypatch):
        s = Settings()
        monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
        p = s.storage_path
        assert p.exists() and p.is_dir()

    def test_reload_clears_cache(self):
        first = settings_mod.get_settings()
        again = settings_mod.get_settings()
        assert first is again  # cached
        reloaded = settings_mod.reload_settings()
        assert reloaded is not first  # fresh instance after cache clear
