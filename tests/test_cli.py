"""Tests for the CLI: time parsing, upload building, and scheduling mode."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import app.config.settings as settings_mod
import main


class TestParseRunAt:
    def test_iso_with_z(self):
        dt = main.parse_run_at("2026-12-31T18:00:00Z")
        assert dt == datetime(2026, 12, 31, 18, 0, 0, tzinfo=UTC)

    def test_iso_with_offset(self):
        dt = main.parse_run_at("2026-01-01T12:00:00+00:00")
        assert dt.tzinfo is not None

    def test_naive_iso_assumed_utc(self):
        dt = main.parse_run_at("2030-06-15T09:30:00")
        assert dt.tzinfo is UTC

    @pytest.mark.parametrize("value,unit,amount", [
        ("+30m", "minutes", 30),
        ("+2h", "hours", 2),
        ("+1d", "days", 1),
        ("+45s", "seconds", 45),
    ])
    def test_relative_offsets(self, value, unit, amount):
        before = datetime.now(UTC)
        dt = main.parse_run_at(value)
        expected = before + timedelta(**{unit: amount})
        # Allow a little slack for execution time.
        assert abs((dt - expected).total_seconds()) < 5

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            main.parse_run_at("not a time")


class TestBuildUpload:
    def _args(self, **over):
        defaults = {
            "upload": False,
            "yt_title": None,
            "yt_description": "",
            "yt_tags": "",
            "yt_privacy": "private",
        }
        defaults.update(over)
        return type("Args", (), defaults)()

    def test_none_when_not_requested(self):
        assert main._build_upload(self._args(upload=False)) is None

    def test_builds_params_with_tags(self):
        u = main._build_upload(self._args(
            upload=True, yt_title="Hi", yt_tags="a, b ,c", yt_privacy="unlisted"
        ))
        assert u is not None
        assert u.enabled is True
        assert u.title == "Hi"
        assert u.tags == ["a", "b", "c"]
        assert u.privacy_status == "unlisted"

    def test_empty_tags(self):
        u = main._build_upload(self._args(upload=True, yt_tags=""))
        assert u.tags == []


class TestScheduleMode:
    @pytest.fixture(autouse=True)
    def _isolate_storage(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
        settings_mod.get_settings.cache_clear()
        yield
        settings_mod.get_settings.cache_clear()

    def test_schedule_enqueues_without_running(self, monkeypatch, capsys):
        # run_pipeline must NOT be called in schedule mode.
        called = {"n": 0}
        monkeypatch.setattr(main, "run_pipeline", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

        rc = main.main(["reading daily", "--schedule", "+1h"])
        assert rc == 0
        assert called["n"] == 0  # did not render

        out = capsys.readouterr().out
        assert "Scheduled job" in out

        # Job persisted.
        from app import scheduler
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].params.topic == "reading daily"

    def test_bad_schedule_value_returns_error(self, capsys):
        rc = main.main(["reading", "--schedule", "garbage"])
        assert rc == 2
        assert "Invalid --schedule" in capsys.readouterr().err
