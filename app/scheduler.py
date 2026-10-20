"""Lightweight job scheduler.

Lets you queue video-generation jobs (optionally with a YouTube upload) to run
at a future time — the "post on a schedule" workflow that similar projects do
with CRON. Jobs are persisted to a JSON file so they survive restarts, and a
single background thread wakes up periodically to run anything that's due.

This is intentionally dependency-free (no Celery/APScheduler) to keep the app
easy to run. For heavy production use you'd swap in a real task queue.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from app.config import get_settings
from app.models import ScheduledJob, UploadParams, VideoParams
from app.task import run_pipeline

_LOCK = threading.RLock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_POLL_SECONDS = 15


def _store_path() -> Path:
    return get_settings().storage_path / "schedule.json"


def _load_jobs() -> list[ScheduledJob]:
    path = _store_path()
    if not path.exists():
        return []
    import json

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read schedule store: {e}")
        return []
    return [ScheduledJob.model_validate(item) for item in raw]


def _save_jobs(jobs: list[ScheduledJob]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "[" + ",".join(j.model_dump_json() for j in jobs) + "]"
    path.write_text(data, encoding="utf-8")


def list_jobs() -> list[ScheduledJob]:
    with _LOCK:
        return _load_jobs()


def schedule_job(
    params: VideoParams,
    run_at: datetime,
    upload: UploadParams | None = None,
) -> ScheduledJob:
    """Persist a new scheduled job and return it."""
    import uuid

    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=UTC)
    job = ScheduledJob(
        job_id=uuid.uuid4().hex[:12],
        params=params,
        upload=upload or UploadParams(),
        run_at=run_at,
    )
    with _LOCK:
        jobs = _load_jobs()
        jobs.append(job)
        _save_jobs(jobs)
    logger.info(f"Scheduled job {job.job_id} for {run_at.isoformat()}")
    return job


def cancel_job(job_id: str) -> bool:
    """Remove a pending job. Returns True if it existed."""
    with _LOCK:
        jobs = _load_jobs()
        remaining = [j for j in jobs if j.job_id != job_id]
        if len(remaining) == len(jobs):
            return False
        _save_jobs(remaining)
    logger.info(f"Cancelled scheduled job {job_id}")
    return True


def _due_jobs(jobs: list[ScheduledJob], now: datetime) -> list[ScheduledJob]:
    return [j for j in jobs if not j.done and j.run_at <= now]


def run_due_jobs(now: datetime | None = None) -> list[str]:
    """Run any jobs whose time has come. Returns the job_ids that were run.

    Exposed separately from the loop so it can be unit-tested deterministically.
    """
    now = now or datetime.now(UTC)
    with _LOCK:
        jobs = _load_jobs()
        due = _due_jobs(jobs, now)

    ran: list[str] = []
    for job in due:
        logger.info(f"Running scheduled job {job.job_id}")
        status = run_pipeline(job.params, upload=job.upload)
        with _LOCK:
            jobs = _load_jobs()
            for j in jobs:
                if j.job_id == job.job_id:
                    j.done = True
                    j.task_id = status.task_id
            _save_jobs(jobs)
        ran.append(job.job_id)
    return ran


def _loop() -> None:
    logger.info("Scheduler loop started")
    while not _STOP.is_set():
        try:
            run_due_jobs()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scheduler iteration failed: {e}")
        _STOP.wait(_POLL_SECONDS)
    logger.info("Scheduler loop stopped")


def start() -> None:
    """Start the background scheduler thread (idempotent)."""
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="vdvideo-scheduler", daemon=True)
        _THREAD.start()


def stop() -> None:
    """Signal the scheduler thread to stop."""
    _STOP.set()
