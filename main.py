"""vdvideo CLI — generate a single video from the command line.

Examples:
    python main.py "the benefits of reading"
    python main.py "space exploration" --aspect 16:9 --voice en-US-GuyNeural
    python main.py "healthy habits" --no-subtitles --bgm-volume 0.2

    # Generate and upload to YouTube when done:
    python main.py "why read daily" --upload --yt-privacy unlisted --yt-title "Read More"

    # Schedule generation (+ optional upload) for later:
    python main.py "monday motivation" --schedule "+2h" --upload
    python main.py "new year tips" --schedule "2026-12-31T18:00:00Z"
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime, timedelta

from app.models import AspectRatio, SubtitlePosition, SubtitleStyle, UploadParams, VideoParams
from app.task import run_pipeline

_REL_RE = re.compile(r"^\+(\d+)([smhd])$")
_REL_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_run_at(value: str) -> datetime:
    """Parse a schedule time: ISO 8601 (e.g. 2026-01-01T12:00:00Z) or a relative
    offset like '+30m', '+2h', '+1d'. Returns a timezone-aware UTC datetime.
    """
    rel = _REL_RE.match(value.strip())
    if rel:
        amount, unit = int(rel.group(1)), rel.group(2)
        return datetime.now(UTC) + timedelta(**{_REL_UNITS[unit]: amount})
    # Accept a trailing 'Z' as UTC.
    iso = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a short video from a topic.")
    p.add_argument("topic", help="Topic or keyword")
    p.add_argument("--language", default="en")
    p.add_argument("--paragraphs", type=int, default=3)
    p.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16")
    p.add_argument("--max-duration", type=int, default=60)
    p.add_argument("--voice", default=None)
    p.add_argument("--voice-rate", type=float, default=1.0)
    p.add_argument("--voice-volume", type=float, default=1.0)
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument("--sub-position", choices=["top", "center", "bottom"], default="bottom")
    p.add_argument("--no-bgm", action="store_true")
    p.add_argument("--bgm-name", default=None)
    p.add_argument("--bgm-volume", type=float, default=0.15)

    yt = p.add_argument_group("YouTube upload")
    yt.add_argument("--upload", action="store_true", help="Upload to YouTube when done")
    yt.add_argument("--yt-title", default=None, help="Video title (defaults to topic)")
    yt.add_argument("--yt-description", default="", help="Video description")
    yt.add_argument("--yt-tags", default="", help="Comma-separated tags")
    yt.add_argument(
        "--yt-privacy", choices=["private", "unlisted", "public"], default="private"
    )

    sch = p.add_argument_group("Scheduling")
    sch.add_argument(
        "--schedule",
        metavar="WHEN",
        default=None,
        help="Schedule instead of running now. ISO 8601 (2026-01-01T12:00:00Z) "
        "or a relative offset (+30m, +2h, +1d).",
    )
    return p


def _build_upload(args) -> UploadParams | None:
    if not args.upload:
        return None
    tags = [t.strip() for t in args.yt_tags.split(",") if t.strip()]
    return UploadParams(
        enabled=True,
        title=args.yt_title,
        description=args.yt_description,
        tags=tags,
        privacy_status=args.yt_privacy,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    params = VideoParams(
        topic=args.topic,
        language=args.language,
        paragraphs=args.paragraphs,
        aspect_ratio=AspectRatio(args.aspect),
        max_duration=args.max_duration,
        voice=args.voice,
        voice_rate=args.voice_rate,
        voice_volume=args.voice_volume,
        subtitles=SubtitleStyle(
            enabled=not args.no_subtitles,
            position=SubtitlePosition(args.sub_position),
        ),
        bgm_enabled=not args.no_bgm,
        bgm_name=args.bgm_name,
        bgm_volume=args.bgm_volume,
    )
    upload = _build_upload(args)

    # Scheduled mode: enqueue and exit immediately.
    if args.schedule:
        try:
            run_at = parse_run_at(args.schedule)
        except ValueError as e:
            print(f"\n❌ Invalid --schedule value {args.schedule!r}: {e}", file=sys.stderr)
            return 2
        from app import scheduler

        job = scheduler.schedule_job(params, run_at, upload=upload)
        print(f"\n🗓️  Scheduled job {job.job_id} for {run_at.isoformat()}")
        print("   Run the API (uvicorn app.router.api:app) to execute scheduled jobs,")
        print("   or trigger due jobs manually with: python -m app.scheduler_run")
        return 0

    # Immediate mode.
    status = run_pipeline(params, upload=upload)
    if status.state.value == "succeeded":
        print(f"\n✅ Video ready: {status.video_path}")
        if status.youtube_video_id:
            print(f"📺 Uploaded: https://youtu.be/{status.youtube_video_id}")
        return 0
    print(f"\n❌ Failed: {status.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
