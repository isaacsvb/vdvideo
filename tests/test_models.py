"""Tests for the Pydantic schemas."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    AspectRatio,
    SubtitlePosition,
    SubtitleStyle,
    TaskState,
    VideoParams,
)


class TestAspectRatio:
    def test_portrait_dimensions(self):
        assert AspectRatio.PORTRAIT.dimensions == (1080, 1920)

    def test_landscape_dimensions(self):
        assert AspectRatio.LANDSCAPE.dimensions == (1920, 1080)

    def test_values(self):
        assert AspectRatio.PORTRAIT.value == "9:16"
        assert AspectRatio.LANDSCAPE.value == "16:9"


class TestVideoParams:
    def test_minimal_defaults(self):
        p = VideoParams(topic="reading")
        assert p.aspect_ratio is AspectRatio.PORTRAIT
        assert p.max_duration == 60
        assert p.bgm_volume == 0.15
        assert p.subtitles.enabled is True

    def test_topic_too_short_rejected(self):
        with pytest.raises(ValidationError):
            VideoParams(topic="x")

    @pytest.mark.parametrize("bad", [-0.1, 1.5])
    def test_bgm_volume_bounds(self, bad):
        with pytest.raises(ValidationError):
            VideoParams(topic="reading", bgm_volume=bad)

    @pytest.mark.parametrize("rate", [0.5, 1.0, 2.0])
    def test_voice_rate_bounds_ok(self, rate):
        assert VideoParams(topic="reading", voice_rate=rate).voice_rate == rate

    @pytest.mark.parametrize("rate", [0.4, 2.1])
    def test_voice_rate_out_of_bounds(self, rate):
        with pytest.raises(ValidationError):
            VideoParams(topic="reading", voice_rate=rate)

    def test_duration_bounds(self):
        with pytest.raises(ValidationError):
            VideoParams(topic="reading", max_duration=5)
        with pytest.raises(ValidationError):
            VideoParams(topic="reading", max_duration=200)

    def test_aspect_from_string(self):
        p = VideoParams(topic="reading", aspect_ratio="16:9")
        assert p.aspect_ratio is AspectRatio.LANDSCAPE


class TestSubtitleStyle:
    def test_defaults(self):
        s = SubtitleStyle()
        assert s.position is SubtitlePosition.BOTTOM
        assert s.enabled is True
        assert s.font_size == 72


def test_task_state_enum():
    assert TaskState.PENDING.value == "pending"
    assert {s.value for s in TaskState} == {"pending", "running", "succeeded", "failed"}
