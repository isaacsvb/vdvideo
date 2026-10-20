"""Media utilities: wire up the bundled ffmpeg binary for moviepy.

Importing this module has the side effect of pointing moviepy at the ffmpeg
binary shipped by imageio-ffmpeg, so the app works without a system ffmpeg.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import imageio_ffmpeg

    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", _FFMPEG)
    os.environ.setdefault("FFMPEG_BINARY", _FFMPEG)
except Exception:  # noqa: BLE001
    _FFMPEG = os.environ.get("FFMPEG_BINARY", "ffmpeg")


def ffmpeg_path() -> str:
    return _FFMPEG


def list_songs(songs_dir: Path) -> list[str]:
    if not songs_dir.exists():
        return []
    return sorted(p.name for p in songs_dir.glob("*.mp3"))


def pick_song(songs_dir: Path, name: str | None) -> Path | None:
    """Return a background-music path by name, or the first available song."""
    songs = list_songs(songs_dir)
    if not songs:
        return None
    if name and name in songs:
        return songs_dir / name
    return songs_dir / songs[0]
