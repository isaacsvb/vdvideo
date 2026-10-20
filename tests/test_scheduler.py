"""Tests for the job scheduler (persistence + due-job execution)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import app.config.settings as settings_mod
from app.models import UploadParams, VideoParams


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    """Fresh scheduler module with storage isolated to a tmp dir."""
    # Point storage at a temp dir so schedule.json doesn't touch the repo.
    monkeypatch.setattr(settings_mod, "PROJECT_ROOT", tmp_path)
    settings_mod.get_settings.cache_clear()
    import app.scheduler as sched

    yield sched
    settings_mod.get_settings.cache_clear()


def _params():
    return VideoParams(topic="scheduled topic")


class TestPersistence:
    def test_empty_initially(self, scheduler):
        assert scheduler.list_jobs() == []

    def test_schedule_and_list(self, scheduler):
        run_at = datetime.now(UTC) + timedelta(hours=1)
        job = scheduler.schedule_job(_params(), run_at)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == job.job_id
        assert jobs[0].params.topic == "scheduled topic"
        assert jobs[0].done is False

    def test_naive_run_at_gets_utc(self, scheduler):
        naive = datetime(2030, 1, 1, 12, 0, 0)  # no tzinfo
        job = scheduler.schedule_job(_params(), naive)
        assert job.run_at.tzinfo is not None

    def test_cancel(self, scheduler):
        job = scheduler.schedule_job(_params(), datetime.now(UTC) + timedelta(hours=1))
        assert scheduler.cancel_job(job.job_id) is True
        assert scheduler.list_jobs() == []

    def test_cancel_missing_returns_false(self, scheduler):
        assert scheduler.cancel_job("nope") is False

    def test_persistence_across_reload(self, scheduler):
        scheduler.schedule_job(_params(), datetime.now(UTC) + timedelta(hours=2))
        # Re-reading from the store returns the persisted job.
        assert len(scheduler.list_jobs()) == 1


class TestRunDueJobs:
    def test_future_job_not_run(self, scheduler, monkeypatch):
        called = []
        monkeypatch.setattr(scheduler, "run_pipeline", lambda *a, **k: called.append(a))
        scheduler.schedule_job(_params(), datetime.now(UTC) + timedelta(hours=1))
        ran = scheduler.run_due_jobs()
        assert ran == []
        assert called == []

    def test_due_job_runs_and_marks_done(self, scheduler, monkeypatch):
        from app.models import TaskStatus

        captured = {}

        def fake_pipeline(params, upload=None):
            captured["topic"] = params.topic
            captured["upload"] = upload
            return TaskStatus(task_id="t-123")

        monkeypatch.setattr(scheduler, "run_pipeline", fake_pipeline)
        past = datetime.now(UTC) - timedelta(minutes=1)
        job = scheduler.schedule_job(_params(), past, upload=UploadParams(enabled=True))

        ran = scheduler.run_due_jobs()
        assert ran == [job.job_id]
        assert captured["topic"] == "scheduled topic"
        assert captured["upload"].enabled is True

        jobs = scheduler.list_jobs()
        assert jobs[0].done is True
        assert jobs[0].task_id == "t-123"

    def test_done_job_not_rerun(self, scheduler, monkeypatch):
        from app.models import TaskStatus

        calls = {"n": 0}

        def fake_pipeline(params, upload=None):
            calls["n"] += 1
            return TaskStatus(task_id="t")

        monkeypatch.setattr(scheduler, "run_pipeline", fake_pipeline)
        past = datetime.now(UTC) - timedelta(minutes=5)
        scheduler.schedule_job(_params(), past)
        scheduler.run_due_jobs()
        scheduler.run_due_jobs()  # second pass should skip the finished job
        assert calls["n"] == 1
