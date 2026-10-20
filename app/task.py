"""Pipeline orchestration.

Runs the end-to-end generation for one VideoParams and reports progress into a
shared in-memory task registry. Designed to be driven either synchronously
(CLI / tests) or in a background thread (API / WebUI).
"""
from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import get_settings
from app.models import TaskState, TaskStatus, UploadParams, VideoParams
from app.services import llm, material, subtitle, voice
from app.util.media import pick_song

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SONGS_DIR = PROJECT_ROOT / "resources" / "songs"

# In-memory task registry (process-local).
_TASKS: dict[str, TaskStatus] = {}
_LOCK = threading.Lock()

ProgressFn = Callable[[int, str], None]


def get_task(task_id: str) -> TaskStatus | None:
    with _LOCK:
        return _TASKS.get(task_id)


def _set(task_id: str, **fields) -> None:
    with _LOCK:
        status = _TASKS.setdefault(task_id, TaskStatus(task_id=task_id))
        for k, v in fields.items():
            setattr(status, k, v)


def run_pipeline(
    params: VideoParams,
    task_id: str | None = None,
    progress: ProgressFn | None = None,
    upload: UploadParams | None = None,
) -> TaskStatus:
    """Execute the full generation pipeline. Returns the final TaskStatus.

    If ``upload`` is provided and enabled, the rendered video is published to
    YouTube after rendering; a failed upload does not discard the video.
    """
    task_id = task_id or uuid.uuid4().hex[:12]
    _set(task_id, state=TaskState.RUNNING, progress=0, message="Starting")

    def report(pct: int, msg: str) -> None:
        _set(task_id, progress=pct, message=msg)
        logger.info(f"[{task_id}] {pct}% {msg}")
        if progress:
            progress(pct, msg)

    work_dir = get_settings().storage_path / "tasks" / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Script + search terms
        report(10, "Writing script with AI")
        script = llm.generate_script(params)
        (work_dir / "script.txt").write_text(script.script, encoding="utf-8")

        # 2. Voiceover
        report(30, "Generating voiceover")
        voice_result = voice.synthesize(script.script, work_dir, voice=params.voice, rate=params.voice_rate)

        # 3. Subtitles
        report(45, "Building subtitles")
        srt_path = subtitle.build_srt(
            script.script, voice_result.duration, voice_result.boundaries, work_dir
        )

        # 4. Stock footage
        report(60, "Finding stock footage")
        clips = material.collect_clips(script.search_terms, params.aspect_ratio)

        # 5. Background music
        bgm_path = pick_song(SONGS_DIR, params.bgm_name) if params.bgm_enabled else None

        # 6. Compose (import here so ffmpeg wiring happens lazily)
        report(75, "Rendering video")
        from app.services import video as video_service

        out_path = video_service.compose(
            params=params,
            clip_paths=clips,
            voice_path=voice_result.audio_path,
            voice_duration=voice_result.duration,
            srt_path=srt_path,
            bgm_path=bgm_path,
            out_dir=work_dir,
        )

        _set(task_id, video_path=str(out_path))

        # 7. Optional YouTube upload (does not fail the whole task if it errors)
        if upload and upload.enabled:
            report(90, "Uploading to YouTube")
            try:
                from app.services import youtube

                video_id = youtube.upload_video(
                    video_path=out_path,
                    title=upload.title or params.topic,
                    description=upload.description,
                    tags=upload.tags,
                    privacy_status=upload.privacy_status,
                )
                _set(task_id, youtube_video_id=video_id)
                logger.info(f"[{task_id}] uploaded to https://youtu.be/{video_id}")
            except Exception as ue:  # noqa: BLE001
                logger.error(f"[{task_id}] YouTube upload failed: {ue}")
                _set(task_id, message=f"Rendered OK, but upload failed: {ue}")

        _set(task_id, state=TaskState.SUCCEEDED, progress=100, message="Done")
        report(100, "Done")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[{task_id}] pipeline failed: {e}\n{traceback.format_exc()}")
        _set(task_id, state=TaskState.FAILED, message="Failed", error=str(e))

    return get_task(task_id)  # type: ignore[return-value]


def run_pipeline_async(params: VideoParams, upload: UploadParams | None = None) -> str:
    """Start the pipeline in a background thread; return the task id immediately."""
    task_id = uuid.uuid4().hex[:12]
    _set(task_id, state=TaskState.PENDING, progress=0, message="Queued")
    threading.Thread(
        target=run_pipeline, args=(params, task_id), kwargs={"upload": upload}, daemon=True
    ).start()
    return task_id
