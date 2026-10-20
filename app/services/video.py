"""Video composition service.

Takes downloaded b-roll clips + voiceover + (optional) subtitles + (optional)
background music and renders a final HD MP4 in the requested aspect ratio.

Uses moviepy, which drives the bundled ffmpeg (imageio-ffmpeg). The ffmpeg path
is configured in app.util.media before moviepy is used.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from moviepy.audio.fx.audio_loop import audio_loop
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.fx.resize import resize

from app.models import SubtitlePosition, SubtitleStyle, VideoParams

# IMPORTANT: import app.util.media *before* moviepy so the bundled ffmpeg binary
# (imageio-ffmpeg) is registered in the environment first. Keep this ordering;
# do not let an autoformatter hoist the moviepy imports above it.
from app.util import media as _media  # noqa: F401  (side-effect: sets FFMPEG_BINARY)


def _fit_clip(clip: VideoFileClip, width: int, height: int):
    """Scale + center-crop a clip to exactly fill width x height."""
    target_ratio = width / height
    clip_ratio = clip.w / clip.h
    if clip_ratio > target_ratio:
        # too wide -> match height, crop width
        scaled = resize(clip, height=height)
        x1 = (scaled.w - width) / 2
        return scaled.crop(x1=x1, y1=0, x2=x1 + width, y2=height)
    # too tall -> match width, crop height
    scaled = resize(clip, width=width)
    y1 = (scaled.h - height) / 2
    return scaled.crop(x1=0, y1=y1, x2=width, y2=y1 + height)


def _build_background(clip_paths: list[Path], width: int, height: int, duration: float):
    """Concatenate clips (looping as needed) to cover ``duration`` seconds."""
    segments = []
    total = 0.0
    idx = 0
    # Give each clip up to ~5s so we cycle through footage.
    per_clip_cap = 5.0
    while total < duration and clip_paths:
        path = clip_paths[idx % len(clip_paths)]
        idx += 1
        try:
            raw = VideoFileClip(str(path))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Skipping unreadable clip {path.name}: {e}")
            if idx > len(clip_paths) * 3:
                break
            continue
        take = min(per_clip_cap, raw.duration, duration - total)
        if take <= 0:
            raw.close()
            break
        piece = _fit_clip(raw.subclip(0, take), width, height).without_audio()
        segments.append(piece)
        total += take

    if not segments:
        raise RuntimeError("Could not build a background track from the downloaded clips.")

    bg = concatenate_videoclips(segments, method="compose")
    return bg.set_duration(duration)


def _subtitle_y(position: SubtitlePosition, height: int, txt_h: int) -> int:
    if position is SubtitlePosition.TOP:
        return int(height * 0.08)
    if position is SubtitlePosition.CENTER:
        return int((height - txt_h) / 2)
    return int(height - txt_h - height * 0.12)  # bottom


def _parse_srt(srt_path: Path) -> list[tuple[float, float, str]]:
    def to_sec(ts: str) -> float:
        hms, ms = ts.split(",")
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    entries: list[tuple[float, float, str]] = []
    blocks = srt_path.read_text(encoding="utf-8").strip().split("\n\n")
    for block in blocks:
        rows = [r for r in block.splitlines() if r.strip()]
        if len(rows) >= 3 and "-->" in rows[1]:
            start, end = (x.strip() for x in rows[1].split("-->"))
            entries.append((to_sec(start), to_sec(end), " ".join(rows[2:])))
    return entries


def _subtitle_clips(srt_path: Path, style: SubtitleStyle, width: int, height: int):
    clips = []
    for start, end, text in _parse_srt(srt_path):
        try:
            txt = TextClip(
                text,
                fontsize=style.font_size,
                color=style.color,
                stroke_color=style.stroke_color,
                stroke_width=style.stroke_width,
                method="caption",
                size=(int(width * 0.9), None),
                align="center",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"TextClip failed (ImageMagick missing?): {e}")
            return []
        y = _subtitle_y(style.position, height, txt.h)
        txt = txt.set_position(("center", y)).set_start(start).set_end(end)
        clips.append(txt)
    return clips


def compose(
    params: VideoParams,
    clip_paths: list[Path],
    voice_path: Path,
    voice_duration: float,
    srt_path: Path | None,
    bgm_path: Path | None,
    out_dir: Path,
) -> Path:
    """Render the final video and return its path."""
    width, height = params.aspect_ratio.dimensions
    # Pad slightly past the voiceover so the last words aren't clipped.
    duration = min(params.max_duration, voice_duration + 0.5)
    logger.info(f"Composing {width}x{height} video, duration ~{duration:.1f}s")

    background = _build_background(clip_paths, width, height, duration)

    # --- audio ---
    voice = AudioFileClip(str(voice_path)).volumex(params.voice_volume)
    audio_tracks = [voice]
    if bgm_path and params.bgm_enabled and bgm_path.exists():
        try:
            music = AudioFileClip(str(bgm_path)).volumex(params.bgm_volume)
            music = audio_loop(music, duration=duration)
            audio_tracks.append(music)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Background music skipped: {e}")
    final_audio = CompositeAudioClip(audio_tracks).set_duration(duration)

    # --- compose video layers ---
    layers = [background]
    if srt_path and params.subtitles.enabled:
        layers.extend(_subtitle_clips(srt_path, params.subtitles, width, height))

    video = CompositeVideoClip(layers, size=(width, height)).set_duration(duration)
    video = video.set_audio(final_audio)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "final.mp4"
    video.write_videofile(
        str(out_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        logger=None,
    )

    # Cleanup (best-effort; closing a clip twice or after render is non-fatal)
    for layer in layers:
        try:
            layer.close()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Clip close failed during cleanup: {e}")
    final_audio.close()
    logger.info(f"Rendered video -> {out_path}")
    return out_path
