"""vdvideo CLI — generate a single video from the command line.

Examples:
    python main.py "the benefits of reading"
    python main.py "space exploration" --aspect 16:9 --voice en-US-GuyNeural
    python main.py "healthy habits" --no-subtitles --bgm-volume 0.2
"""
from __future__ import annotations

import argparse
import sys

from app.models import AspectRatio, SubtitlePosition, SubtitleStyle, VideoParams
from app.task import run_pipeline


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
    return p


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
    status = run_pipeline(params)
    if status.state.value == "succeeded":
        print(f"\n✅ Video ready: {status.video_path}")
        return 0
    print(f"\n❌ Failed: {status.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
