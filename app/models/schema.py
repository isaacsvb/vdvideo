"""Pydantic schemas shared across the app and API."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class AspectRatio(str, Enum):
    PORTRAIT = "9:16"   # TikTok / YouTube Shorts / Reels
    LANDSCAPE = "16:9"  # YouTube

    @property
    def dimensions(self) -> tuple[int, int]:
        """HD dimensions (width, height) for this aspect ratio."""
        return (1080, 1920) if self is AspectRatio.PORTRAIT else (1920, 1080)


class SubtitlePosition(str, Enum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class SubtitleStyle(BaseModel):
    enabled: bool = True
    font_size: int = 72
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 4
    position: SubtitlePosition = SubtitlePosition.BOTTOM


class VideoParams(BaseModel):
    """Everything needed to generate one video."""

    # Content
    topic: str = Field(..., min_length=2, description="Topic or keyword for the video")
    language: str = Field("en", description="Script language code, e.g. 'en', 'es'")
    paragraphs: int = Field(3, ge=1, le=8, description="Approx. number of script sentences/paragraphs")

    # Format
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT
    max_duration: int = Field(60, ge=10, le=180, description="Target max video length in seconds")

    # Voice
    voice: str | None = Field(None, description="TTS voice short-name; defaults to config")
    voice_rate: float = Field(1.0, ge=0.5, le=2.0, description="Speaking rate multiplier")
    voice_volume: float = Field(1.0, ge=0.0, le=1.0, description="Voiceover volume (0-1)")

    # Subtitles
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)

    # Music
    bgm_enabled: bool = True
    bgm_name: str | None = Field(None, description="Background music file in resources/songs")
    bgm_volume: float = Field(0.15, ge=0.0, le=1.0, description="Background music volume (0-1)")


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class UploadParams(BaseModel):
    """Optional YouTube-upload settings attached to a generation job."""
    enabled: bool = False
    title: str | None = Field(None, description="Video title; defaults to the topic")
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy_status: str = Field("private", pattern="^(private|unlisted|public)$")


class TaskStatus(BaseModel):
    task_id: str
    state: TaskState = TaskState.PENDING
    progress: int = 0            # 0-100
    message: str = ""
    video_path: str | None = None
    youtube_video_id: str | None = None
    error: str | None = None


class ScriptResult(BaseModel):
    """Output of the LLM step."""
    script: str
    search_terms: list[str]


class ScheduledJob(BaseModel):
    """A generation job scheduled to run at a future time."""
    job_id: str
    params: VideoParams
    upload: UploadParams = Field(default_factory=UploadParams)
    run_at: datetime = Field(..., description="UTC time to run the job")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    done: bool = False
    task_id: str | None = None
