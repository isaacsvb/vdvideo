"""FastAPI application exposing the generation pipeline as a REST service."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app import __version__
from app.models import TaskStatus, VideoParams
from app.task import get_task, run_pipeline_async

app = FastAPI(title="vdvideo API", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/videos", response_model=dict)
def create_video(params: VideoParams) -> dict:
    """Queue a video generation job; returns a task id to poll."""
    task_id = run_pipeline_async(params)
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
