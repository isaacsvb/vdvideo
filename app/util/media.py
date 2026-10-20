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


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_FONTS = [
    _PROJECT_ROOT / "resources" / "fonts" / "DejaVuSans.ttf",
    _PROJECT_ROOT / "resources" / "fonts" / "DejaVuSans-Bold.ttf",
]
# Common system font locations to fall back on (Linux, macOS, Windows).
_SYSTEM_FONT_GLOBS = [
    "/usr/share/fonts/**/DejaVuSans.ttf",
    "/usr/share/fonts/**/*.ttf",
    "/Library/Fonts/*.ttf",
    "/System/Library/Fonts/Supplemental/*.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/*.ttf",
]


def default_font() -> str | None:
    """Return a path to a usable TTF font for subtitles.

    Prefers the font bundled with the project (so captions render identically
    everywhere), then falls back to common system fonts. Returns None only if
    nothing is found, in which case subtitles are skipped gracefully.
    """
    import glob

    for font in _BUNDLED_FONTS:
        if font.exists():
            return str(font)
    for pattern in _SYSTEM_FONT_GLOBS:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None


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
