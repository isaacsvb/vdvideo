"""YouTube upload service.

Uploads a finished video to YouTube using the **official YouTube Data API v3**
with OAuth 2.0. This is intentionally different from the Selenium-based approach
some similar projects use: the official API is stable, supported, and doesn't
break when the web UI changes.

First-time setup (one-off):
  1. In Google Cloud Console, create an OAuth *Desktop app* credential with the
     "YouTube Data API v3" enabled, and download the client-secrets JSON.
  2. Point `[youtube] client_secrets_file` (or env YOUTUBE_CLIENT_SECRETS_FILE)
     at that file.
  3. The first upload opens a browser for consent; the token is then cached in
     `[youtube] token_file` so later uploads are non-interactive.

The Google client libraries are an *optional* dependency — this module only
imports them inside functions, so the rest of the app works without them.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.config import get_settings

# Scope required to upload videos.
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_VALID_PRIVACY = {"private", "unlisted", "public"}


class YouTubeUploadError(RuntimeError):
    """Raised when an upload cannot be performed."""


def _require_libs():
    """Import the Google client libraries, with a helpful error if missing."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        raise YouTubeUploadError(
            "YouTube upload requires the Google client libraries. Install them with:\n"
            "  pip install google-api-python-client google-auth-oauthlib"
        ) from e
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload


def _get_credentials(interactive: bool = True):
    """Load cached OAuth credentials, refreshing or running the flow as needed."""
    Request, Credentials, InstalledAppFlow, _build, _media = _require_libs()
    cfg = get_settings().youtube

    if not cfg.client_secrets_file:
        raise YouTubeUploadError(
            "No YouTube client-secrets file configured. Set [youtube] "
            "client_secrets_file or the YOUTUBE_CLIENT_SECRETS_FILE env var."
        )
    secrets_path = Path(cfg.client_secrets_file)
    if not secrets_path.exists():
        raise YouTubeUploadError(f"Client-secrets file not found: {secrets_path}")

    token_path = get_settings().storage_path / cfg.token_file
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired YouTube token")
        creds.refresh(Request())
    else:
        if not interactive:
            raise YouTubeUploadError(
                "No valid cached YouTube token and interactive auth is disabled. "
                "Run an upload once interactively to authorize."
            )
        logger.info("Starting YouTube OAuth consent flow (opens a browser)")
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), _SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info(f"Cached YouTube token at {token_path}")
    return creds


def upload_video(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy_status: str | None = None,
    category_id: str | None = None,
    interactive: bool = True,
) -> str:
    """Upload a video to YouTube and return the resulting video ID.

    Raises YouTubeUploadError on any configuration or API problem.
    """
    if not video_path.exists():
        raise YouTubeUploadError(f"Video file not found: {video_path}")

    cfg = get_settings().youtube
    privacy = (privacy_status or cfg.privacy_status).lower()
    if privacy not in _VALID_PRIVACY:
        raise YouTubeUploadError(
            f"Invalid privacy_status {privacy!r}; must be one of {sorted(_VALID_PRIVACY)}"
        )
    # YouTube caps titles at 100 characters.
    title = title[:100]

    _Request, _Creds, _Flow, build, MediaFileUpload = _require_libs()
    creds = _get_credentials(interactive=interactive)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id or cfg.category_id,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    logger.info(f"Uploading {video_path.name} to YouTube (privacy={privacy})")
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id", "")
    logger.info(f"Upload complete: https://youtu.be/{video_id}")
    return video_id
