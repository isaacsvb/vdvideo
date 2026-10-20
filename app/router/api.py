"""FastAPI application exposing the generation pipeline as a REST service."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field

from app import __version__
from app import scheduler as sched
from app.models import ScheduledJob, TaskStatus, UploadParams, VideoParams
from app.task import get_task, run_pipeline_async


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Launch the background scheduler so any persisted jobs run when due.
    sched.start()
    yield
    sched.stop()


app = FastAPI(title="vdvideo API", version=__version__, lifespan=lifespan)


class CreateVideoRequest(VideoParams):
    """VideoParams plus an optional YouTube-upload block (flat request body)."""
    upload: UploadParams | None = None


class ScheduleRequest(VideoParams):
    """VideoParams plus a run time and optional upload block."""
    run_at: datetime = Field(..., description="UTC time to run the job")
    upload: UploadParams | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/videos", response_model=dict)
def create_video(req: CreateVideoRequest) -> dict:
    """Queue a video generation job; returns a task id to poll.

    The body is a flat `VideoParams` object; add an optional `upload` field to
    publish to YouTube when rendering finishes.
    """
    upload = req.upload
    params = VideoParams(**req.model_dump(exclude={"upload"}))
    task_id = run_pipeline_async(params, upload=upload)
    return {"task_id": task_id}


@app.get("/tasks/{task_id}", response_model=TaskStatus)
def task_status(task_id: str) -> TaskStatus:
    status = get_task(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@app.get("/tasks/{task_id}/download")
def download(task_id: str) -> FileResponse:
    status = get_task(task_id)
    if status is None or not status.video_path:
        raise HTTPException(status_code=404, detail="Video not ready")
    path = Path(status.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(str(path), media_type="video/mp4", filename=f"{task_id}.mp4")


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #
@app.post("/schedule", response_model=ScheduledJob)
def create_schedule(req: ScheduleRequest) -> ScheduledJob:
    """Schedule a generation (and optional upload) job to run at a future time."""
    params = VideoParams(**req.model_dump(exclude={"upload", "run_at"}))
    return sched.schedule_job(params, req.run_at, upload=req.upload)


@app.get("/schedule", response_model=list[ScheduledJob])
def list_schedule() -> list[ScheduledJob]:
    return sched.list_jobs()


@app.delete("/schedule/{job_id}", response_model=dict)
def delete_schedule(job_id: str) -> dict:
    if not sched.cancel_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"cancelled": job_id}
