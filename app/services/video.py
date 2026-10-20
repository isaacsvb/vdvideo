"""Video composition service.

Takes downloaded b-roll clips + voiceover + (optional) subtitles + (optional)
background music and renders a final HD MP4 in the requested aspect ratio.

Uses moviepy, which drives the bundled ffmpeg (imageio-ffmpeg). The ffmpeg path
is configured in app.util.media before moviepy is used.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.models import FitMode, SubtitlePosition, SubtitleStyle, VideoParams

# IMPORTANT: import app.util.media *before* moviepy so the bundled ffmpeg binary
# (imageio-ffmpeg) is registered in the environment first. Keep this ordering;
# do not let an autoformatter hoist the moviepy imports above it.
from app.util import media as _media

# moviepy 2.x: everything imports from the top-level `moviepy` package
# (the old `moviepy.editor` namespace was removed), and effects are classes
# applied via `with_effects([...])`.
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
)


def _scale_to_fill(clip, width: int, height: int):
    """Scale + center-crop so the clip exactly fills width x height (crops edges)."""
    target_ratio = width / height
    clip_ratio = clip.w / clip.h
    if clip_ratio > target_ratio:
        scaled = clip.resized(height=height)
        x1 = (scaled.w - width) / 2
        return scaled.cropped(x1=x1, y1=0, x2=x1 + width, y2=height)
    scaled = clip.resized(width=width)
    y1 = (scaled.h - height) / 2
    return scaled.cropped(x1=0, y1=y1, x2=width, y2=y1 + height)


def _scale_to_fit(clip, width: int, height: int):
    """Scale so the whole clip fits inside width x height (no crop; may be smaller)."""
    target_ratio = width / height
    clip_ratio = clip.w / clip.h
    if clip_ratio > target_ratio:
        return clip.resized(width=width)   # limited by width
    return clip.resized(height=height)      # limited by height


def _blur_frame(frame, radius: int = 35):
    """Gaussian-blur a single RGB frame using Pillow (no extra dependency)."""
    from PIL import Image, ImageFilter

    img = Image.fromarray(frame).filter(ImageFilter.GaussianBlur(radius))
    import numpy as np

    return np.array(img)


def _fit_clip(clip, width: int, height: int, mode: FitMode):
    """Fit ``clip`` to width x height according to the chosen FitMode.

    - CROP: fill the frame, cropping the overflow (original behaviour).
    - BLUR: show the whole frame centered over a blurred, filled copy of itself
      (the "Reels/Shorts" look — nothing is cropped or left black).
    - PAD : show the whole frame centered over solid black bars.
    """
    if mode is FitMode.CROP:
        return _scale_to_fill(clip, width, height)

    foreground = _scale_to_fit(clip, width, height).with_position("center")

    if mode is FitMode.PAD:
        background = ColorClip(size=(width, height), color=(0, 0, 0)).with_duration(clip.duration)
    else:  # BLUR
        background = (
            _scale_to_fill(clip, width, height)
            .image_transform(_blur_frame)
            .with_duration(clip.duration)
        )

    return CompositeVideoClip([background, foreground], size=(width, height)).with_duration(
        clip.duration
    )


def _build_background(clip_paths: list[Path], width: int, height: int, duration: float, mode: FitMode):
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
        piece = _fit_clip(raw.subclipped(0, take), width, height, mode).without_audio()
        segments.append(piece)
        total += take

    if not segments:
        raise RuntimeError("Could not build a background track from the downloaded clips.")

    bg = concatenate_videoclips(segments, method="compose")
    return bg.with_duration(duration)


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
    font = _media.default_font()
    if font is None:
        logger.warning("No TTF font found for subtitles; skipping burned-in captions.")
        return []
    clips = []
    for start, end, text in _parse_srt(srt_path):
        try:
            # moviepy 2.x: font is a path, `font_size` (not fontsize), and text
            # rendering uses Pillow — no system ImageMagick required.
            txt = TextClip(
                font=font,
                text=text,
                font_size=style.font_size,
                color=style.color,
                stroke_color=style.stroke_color,
                stroke_width=style.stroke_width,
                method="caption",
                size=(int(width * 0.9), None),
                text_align="center",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"TextClip failed: {e}")
            return []
        y = _subtitle_y(style.position, height, txt.h)
        txt = txt.with_position(("center", y)).with_start(start).with_end(end)
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

    background = _build_background(clip_paths, width, height, duration, params.fit_mode)

    # --- audio --- (moviepy 2.x: volume/loop are effect classes)
    voice = AudioFileClip(str(voice_path)).with_effects([afx.MultiplyVolume(params.voice_volume)])
    audio_tracks = [voice]
    if bgm_path and params.bgm_enabled and bgm_path.exists():
        try:
            music = AudioFileClip(str(bgm_path)).with_effects([
                afx.MultiplyVolume(params.bgm_volume),
                afx.AudioLoop(duration=duration),
            ])
            audio_tracks.append(music)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Background music skipped: {e}")
    final_audio = CompositeAudioClip(audio_tracks).with_duration(duration)

    # --- compose video layers ---
    layers = [background]
    if srt_path and params.subtitles.enabled:
        layers.extend(_subtitle_clips(srt_path, params.subtitles, width, height))

    video = CompositeVideoClip(layers, size=(width, height)).with_duration(duration)
    video = video.with_audio(final_audio)

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
