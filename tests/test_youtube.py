"""Tests for the YouTube upload service (config/validation; no network)."""
from __future__ import annotations

import pytest

import app.config.settings as settings_mod
from app.services import youtube
from app.services.youtube import YouTubeUploadError


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


class TestUploadValidation:
    def test_missing_video_file_raises(self, tmp_path):
        with pytest.raises(YouTubeUploadError, match="Video file not found"):
            youtube.upload_video(tmp_path / "nope.mp4", title="x")

    def test_invalid_privacy_raises(self, tmp_path, monkeypatch):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        # Avoid import error path; pretend libs are present.
        monkeypatch.setattr(youtube, "_require_libs", lambda: (None,) * 5)
        with pytest.raises(YouTubeUploadError, match="Invalid privacy_status"):
            youtube.upload_video(video, title="x", privacy_status="secret")

    def test_missing_libs_gives_helpful_error(self, tmp_path, monkeypatch):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        def boom():
            raise YouTubeUploadError("install libs")

        monkeypatch.setattr(youtube, "_require_libs", boom)
        with pytest.raises(YouTubeUploadError):
            youtube.upload_video(video, title="x")


class TestCredentials:
    def test_no_client_secrets_configured(self, tmp_path, monkeypatch):
        # Libs importable, but no client-secrets path configured.
        monkeypatch.setattr(youtube, "_require_libs", lambda: (object(),) * 5)
        monkeypatch.delenv("YOUTUBE_CLIENT_SECRETS_FILE", raising=False)
        with pytest.raises(YouTubeUploadError, match="client-secrets"):
            youtube._get_credentials(interactive=False)

    def test_missing_secrets_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(youtube, "_require_libs", lambda: (object(),) * 5)
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_FILE", str(tmp_path / "absent.json"))
        settings_mod.get_settings.cache_clear()
        with pytest.raises(YouTubeUploadError, match="not found"):
            youtube._get_credentials(interactive=False)
