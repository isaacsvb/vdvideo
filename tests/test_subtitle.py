"""Tests for subtitle (.srt) generation."""
from __future__ import annotations

import re
from pathlib import Path

from app.services import subtitle
from app.services.subtitle import _even_split, _fmt_ts, _group_boundaries

TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}$")


class TestFmtTimestamp:
    def test_zero(self):
        assert _fmt_ts(0) == "00:00:00,000"

    def test_subsecond(self):
        assert _fmt_ts(1.5) == "00:00:01,500"

    def test_minutes_and_hours(self):
        assert _fmt_ts(3661.25) == "01:01:01,250"

    def test_negative_clamped(self):
        assert _fmt_ts(-5) == "00:00:00,000"

    def test_format_shape(self):
        assert TS_RE.match(_fmt_ts(12.345))


class TestGrouping:
    def test_groups_respect_word_limit(self, word_boundaries):
        lines = _group_boundaries(word_boundaries)
        assert len(lines) >= 1
        for _start, _end, text in lines:
            assert len(text.split()) <= 7

    def test_timing_monotonic(self, word_boundaries):
        lines = _group_boundaries(word_boundaries)
        for start, end, _ in lines:
            assert end >= start
        # line starts should be non-decreasing
        starts = [s for s, _, _ in lines]
        assert starts == sorted(starts)

    def test_all_words_preserved(self, word_boundaries):
        lines = _group_boundaries(word_boundaries)
        joined = " ".join(text for _, _, text in lines).split()
        original = [w.text for w in word_boundaries]
        assert joined == original


class TestEvenSplit:
    def test_empty_text(self):
        assert _even_split("", 10.0) == []

    def test_covers_duration(self):
        lines = _even_split("one two three four five six seven eight nine ten", 10.0)
        assert lines
        # last end should be ~ duration
        assert abs(lines[-1][1] - 10.0) < 1e-6

    def test_words_preserved(self):
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        lines = _even_split(text, 8.0)
        joined = " ".join(t for _, _, t in lines)
        assert joined.split() == text.split()


class TestBuildSrt:
    def test_returns_none_when_no_text(self, tmp_out: Path):
        assert subtitle.build_srt("", 5.0, [], tmp_out) is None

    def test_writes_valid_srt_from_boundaries(self, tmp_out: Path, word_boundaries):
        path = subtitle.build_srt("ignored", 5.0, word_boundaries, tmp_out)
        assert path is not None and path.exists()
        content = path.read_text(encoding="utf-8")
        # Must contain an index, a timestamp line with -->, and text.
        assert "1\n" in content
        assert "-->" in content
        # Every timestamp line is well-formed.
        for line in content.splitlines():
            if "-->" in line:
                left, right = (x.strip() for x in line.split("-->"))
                assert TS_RE.match(left) and TS_RE.match(right)

    def test_fallback_even_split_when_no_boundaries(self, tmp_out: Path):
        path = subtitle.build_srt("one two three four five", 5.0, [], tmp_out)
        assert path is not None and path.exists()
        assert "-->" in path.read_text(encoding="utf-8")
