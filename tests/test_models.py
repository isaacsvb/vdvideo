"""Tests for the Pydantic schemas."""
from __future__ import annotations

from datetime import UTC

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
        from app.models import FitMode

        p = VideoParams(topic="reading")
        assert p.aspect_ratio is AspectRatio.PORTRAIT
        assert p.fit_mode is FitMode.BLUR  # no-crop default
        assert p.max_duration == 60
        assert p.bgm_volume == 0.15
        assert p.subtitles.enabled is True

    def test_fit_mode_from_string(self):
        from app.models import FitMode

        assert VideoParams(topic="reading", fit_mode="crop").fit_mode is FitMode.CROP
        assert VideoParams(topic="reading", fit_mode="pad").fit_mode is FitMode.PAD

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


class TestUploadParams:
    def test_defaults_disabled(self):
        from app.models import UploadParams

        u = UploadParams()
        assert u.enabled is False
        assert u.privacy_status == "private"
        assert u.tags == []

    @pytest.mark.parametrize("status", ["private", "unlisted", "public"])
    def test_valid_privacy(self, status):
        from app.models import UploadParams

        assert UploadParams(privacy_status=status).privacy_status == status

    def test_invalid_privacy_rejected(self):
        from app.models import UploadParams

        with pytest.raises(ValidationError):
            UploadParams(privacy_status="secret")


class TestScheduledJob:
    def test_requires_run_at(self):
        from app.models import ScheduledJob

        with pytest.raises(ValidationError):
            ScheduledJob(job_id="j1", params=VideoParams(topic="reading"))

    def test_round_trip_json(self):
        from datetime import datetime

        from app.models import ScheduledJob

        job = ScheduledJob(
            job_id="j1",
            params=VideoParams(topic="reading"),
            run_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        restored = ScheduledJob.model_validate_json(job.model_dump_json())
        assert restored.job_id == "j1"
        assert restored.params.topic == "reading"
        assert restored.done is False
