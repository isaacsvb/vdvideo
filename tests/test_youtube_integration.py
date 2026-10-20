"""Mocked integration test for the YouTube upload flow.

This exercises the *entire* upload code path against fakes that mimic the real
`googleapiclient` / `google-auth` contract — the resumable `next_chunk()` loop,
the request `body` shape, credential caching, and token refresh — without ever
touching the network or needing real OAuth credentials. It's the closest we can
get to a real upload without a Google account and a human consent step.
"""
from __future__ import annotations

import json
from typing import ClassVar

import pytest

import app.config.settings as settings_mod
from app.services import youtube


# --------------------------------------------------------------------------- #
# Fakes that mimic the google-api-python-client contract
# --------------------------------------------------------------------------- #
class FakeStatus:
    """Mimics googleapiclient's upload status object."""
    def __init__(self, progress: float):
        self._progress = progress

    def progress(self) -> float:
        return self._progress


class FakeInsertRequest:
    """Mimics the resumable request returned by videos().insert().

    Yields incremental progress across several next_chunk() calls, then returns
    the final response dict — exactly how a real resumable upload behaves.
    """
    def __init__(self, response_id: str = "VIDEO123", chunks: int = 3):
        self._response = {"id": response_id}
        self._chunks = chunks
        self._calls = 0

    def next_chunk(self):
        self._calls += 1
        if self._calls < self._chunks:
            # Still uploading: (status, None)
            return FakeStatus(self._calls / self._chunks), None
        # Done: (None, response)
        return None, self._response


class FakeVideos:
    def __init__(self, recorder: dict, request: FakeInsertRequest):
        self._recorder = recorder
        self._request = request

    def insert(self, part, body, media_body):
        # Record exactly what the service sent so the test can assert on it.
        self._recorder["part"] = part
        self._recorder["body"] = body
        self._recorder["media_body"] = media_body
        return self._request


class FakeYouTubeClient:
    def __init__(self, recorder: dict, request: FakeInsertRequest):
        self._videos = FakeVideos(recorder, request)

    def videos(self):
        return self._videos


class FakeMediaFileUpload:
    """Records the media-upload construction args."""
    last_kwargs: ClassVar[dict] = {}

    def __init__(self, path, chunksize, resumable, mimetype):
        FakeMediaFileUpload.last_kwargs = {
            "path": path,
            "chunksize": chunksize,
            "resumable": resumable,
            "mimetype": mimetype,
        }


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


@pytest.fixture
def valid_creds_setup(tmp_path, monkeypatch):
    """Configure a client-secrets file and a cached, valid token on disk."""
    monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
    settings_mod.get_settings.cache_clear()

    secrets = tmp_path / "client_secrets.json"
    secrets.write_text('{"installed": {"client_id": "x"}}', encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_FILE", str(secrets))
    settings_mod.get_settings.cache_clear()

    # Pre-seed a cached token so no interactive flow is needed.
    storage = settings_mod.get_settings().storage_path
    (storage / "youtube_token.json").write_text('{"token": "cached"}', encoding="utf-8")
    return tmp_path


def _install_fakes(monkeypatch, *, creds, recorder, request):
    """Point _require_libs() at our fakes and make build() return the fake client."""
    class FakeCredentials:
        @staticmethod
        def from_authorized_user_file(path, scopes):
            return creds

    def fake_build(service, version, credentials=None):
        recorder["build"] = {"service": service, "version": version, "creds": credentials}
        return FakeYouTubeClient(recorder, request)

    # Request must be callable: the service does `creds.refresh(Request())`.
    class FakeRequest:
        def __init__(self):
            pass

    monkeypatch.setattr(
        youtube,
        "_require_libs",
        lambda: (FakeRequest, FakeCredentials, object(), fake_build, FakeMediaFileUpload),
    )


class TestUploadFlow:
    def test_full_upload_with_cached_valid_token(self, valid_creds_setup, monkeypatch):
        recorder: dict = {}
        request = FakeInsertRequest(response_id="abc123XYZ", chunks=3)

        class Creds:
            valid = True
            expired = False
            refresh_token = None

        _install_fakes(monkeypatch, creds=Creds(), recorder=recorder, request=request)

        video = valid_creds_setup / "final.mp4"
        video.write_bytes(b"\x00\x00fakevideo")

        video_id = youtube.upload_video(
            video_path=video,
            title="My Great Short",
            description="A test description",
            tags=["reading", "books"],
            privacy_status="unlisted",
            category_id="27",
        )

        # 1. Returned the id from the final response chunk.
        assert video_id == "abc123XYZ"

        # 2. build() was called for the right API.
        assert recorder["build"]["service"] == "youtube"
        assert recorder["build"]["version"] == "v3"

        # 3. The request body matches the YouTube Data API v3 contract.
        body = recorder["body"]
        assert recorder["part"] == "snippet,status"
        assert body["snippet"]["title"] == "My Great Short"
        assert body["snippet"]["description"] == "A test description"
        assert body["snippet"]["tags"] == ["reading", "books"]
        assert body["snippet"]["categoryId"] == "27"
        assert body["status"]["privacyStatus"] == "unlisted"
        assert body["status"]["selfDeclaredMadeForKids"] is False

        # 4. MediaFileUpload built with resumable settings and mp4 mimetype.
        mk = FakeMediaFileUpload.last_kwargs
        assert mk["resumable"] is True
        assert mk["mimetype"] == "video/mp4"
        assert mk["chunksize"] == -1

        # 5. The resumable loop ran across multiple chunks (3 next_chunk calls).
        assert request._calls == 3

    def test_title_truncated_to_100_chars(self, valid_creds_setup, monkeypatch):
        recorder: dict = {}

        class Creds:
            valid = True
            expired = False
            refresh_token = None

        _install_fakes(monkeypatch, creds=Creds(), recorder=recorder, request=FakeInsertRequest())

        video = valid_creds_setup / "v.mp4"
        video.write_bytes(b"x")

        long_title = "A" * 250
        youtube.upload_video(video_path=video, title=long_title)
        assert len(recorder["body"]["snippet"]["title"]) == 100

    def test_default_privacy_and_category_from_config(self, valid_creds_setup, monkeypatch):
        recorder: dict = {}

        class Creds:
            valid = True
            expired = False
            refresh_token = None

        _install_fakes(monkeypatch, creds=Creds(), recorder=recorder, request=FakeInsertRequest())

        video = valid_creds_setup / "v.mp4"
        video.write_bytes(b"x")

        # No privacy/category passed -> fall back to config defaults.
        youtube.upload_video(video_path=video, title="t")
        assert recorder["body"]["status"]["privacyStatus"] == "private"  # config default
        assert recorder["body"]["snippet"]["categoryId"] == "22"          # config default


class TestTokenRefresh:
    def test_expired_token_is_refreshed_and_recached(self, valid_creds_setup, monkeypatch):
        refreshed = {"done": False}

        class ExpiredCreds:
            valid = False
            expired = True
            refresh_token = "refresh-abc"

            def refresh(self, request):
                refreshed["done"] = True
                # After refresh, becomes valid.
                self.valid = True

            def to_json(self):
                return '{"token": "refreshed"}'

        recorder: dict = {}
        _install_fakes(
            monkeypatch, creds=ExpiredCreds(), recorder=recorder, request=FakeInsertRequest()
        )

        video = valid_creds_setup / "v.mp4"
        video.write_bytes(b"x")

        vid = youtube.upload_video(video_path=video, title="t")
        assert vid == "VIDEO123"
        assert refreshed["done"] is True

        # The refreshed token was written back to the cache.
        token_path = settings_mod.get_settings().storage_path / "youtube_token.json"
        assert json.loads(token_path.read_text())["token"] == "refreshed"


class TestInteractiveFlow:
    def test_consent_flow_runs_when_no_cached_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
        settings_mod.get_settings.cache_clear()
        secrets = tmp_path / "client_secrets.json"
        secrets.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_FILE", str(secrets))
        settings_mod.get_settings.cache_clear()
        # NOTE: no token file on disk -> interactive flow must run.

        flow_ran = {"done": False}

        class NewCreds:
            valid = True
            expired = False
            refresh_token = None

            def to_json(self):
                return '{"token": "fresh-from-consent"}'

        class FakeFlow:
            @staticmethod
            def from_client_secrets_file(path, scopes):
                return FakeFlow()

            def run_local_server(self, port):
                flow_ran["done"] = True
                return NewCreds()

        recorder: dict = {}

        def fake_build(service, version, credentials=None):
            return FakeYouTubeClient(recorder, FakeInsertRequest())

        class FakeCredentials:
            @staticmethod
            def from_authorized_user_file(path, scopes):  # pragma: no cover - not reached
                raise AssertionError("should not read a token that doesn't exist")

        monkeypatch.setattr(
            youtube,
            "_require_libs",
            lambda: (object(), FakeCredentials, FakeFlow, fake_build, FakeMediaFileUpload),
        )

        video = tmp_path / "v.mp4"
        video.write_bytes(b"x")

        vid = youtube.upload_video(video_path=video, title="t", interactive=True)
        assert vid == "VIDEO123"
        assert flow_ran["done"] is True
        # Token from consent was cached.
        token_path = settings_mod.get_settings().storage_path / "youtube_token.json"
        assert json.loads(token_path.read_text())["token"] == "fresh-from-consent"

    def test_non_interactive_without_token_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
        settings_mod.get_settings.cache_clear()
        secrets = tmp_path / "client_secrets.json"
        secrets.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_FILE", str(secrets))
        settings_mod.get_settings.cache_clear()

        class FakeCredentials:
            @staticmethod
            def from_authorized_user_file(path, scopes):  # pragma: no cover
                raise AssertionError("no token present")

        monkeypatch.setattr(
            youtube,
            "_require_libs",
            lambda: (object(), FakeCredentials, object(), object(), FakeMediaFileUpload),
        )

        video = tmp_path / "v.mp4"
        video.write_bytes(b"x")

        with pytest.raises(youtube.YouTubeUploadError, match="interactive auth is disabled"):
            youtube.upload_video(video_path=video, title="t", interactive=False)
