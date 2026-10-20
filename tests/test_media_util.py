"""Tests for media utilities: ffmpeg wiring and music selection."""
from __future__ import annotations

from pathlib import Path

from app.util import media


def test_ffmpeg_path_is_set():
    p = media.ffmpeg_path()
    assert isinstance(p, str) and p


class TestListSongs:
    def test_missing_dir_returns_empty(self, tmp_path: Path):
        assert media.list_songs(tmp_path / "nope") == []

    def test_lists_only_mp3_sorted(self, tmp_path: Path):
        (tmp_path / "b.mp3").write_bytes(b"x")
        (tmp_path / "a.mp3").write_bytes(b"x")
        (tmp_path / "note.txt").write_text("not music")
        assert media.list_songs(tmp_path) == ["a.mp3", "b.mp3"]


class TestPickSong:
    def test_none_when_empty(self, tmp_path: Path):
        assert media.pick_song(tmp_path, None) is None

    def test_named_match(self, tmp_path: Path):
        (tmp_path / "calm.mp3").write_bytes(b"x")
        (tmp_path / "upbeat.mp3").write_bytes(b"x")
        assert media.pick_song(tmp_path, "upbeat.mp3") == tmp_path / "upbeat.mp3"

    def test_falls_back_to_first_when_name_missing(self, tmp_path: Path):
        (tmp_path / "a.mp3").write_bytes(b"x")
        (tmp_path / "b.mp3").write_bytes(b"x")
        assert media.pick_song(tmp_path, "does_not_exist.mp3") == tmp_path / "a.mp3"

    def test_falls_back_to_first_when_name_none(self, tmp_path: Path):
        (tmp_path / "only.mp3").write_bytes(b"x")
        assert media.pick_song(tmp_path, None) == tmp_path / "only.mp3"
