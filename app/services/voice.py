"""Text-to-speech service.

Default back-end is edge-tts (free, no API key) which also returns word-level
boundary timings we use to build subtitles. OpenAI TTS is available as an
alternative (no per-word timings; subtitles fall back to even splitting).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.config import get_settings


@dataclass
class WordBoundary:
    text: str
    start: float   # seconds
    end: float     # seconds


@dataclass
class VoiceResult:
    audio_path: Path
    duration: float
    boundaries: list[WordBoundary]


def list_edge_voices_sync(language_prefix: str = "en") -> list[str]:
    """Return available edge-tts voices filtered by language prefix."""
    import edge_tts

    async def _run() -> list[str]:
        voices = await edge_tts.list_voices()
        names = [v["ShortName"] for v in voices if v["ShortName"].lower().startswith(language_prefix.lower())]
        return sorted(names)

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not list edge voices: {e}")
        return []


def _rate_to_edge(rate: float) -> str:
    """Convert a 0.5-2.0 multiplier into edge-tts '+NN%' / '-NN%' form."""
    pct = round((rate - 1.0) * 100)
    return f"{pct:+d}%"


async def _edge_synthesize(text: str, voice: str, rate: str, out_path: Path) -> list[WordBoundary]:
    import edge_tts

    # Request word-level timings explicitly; edge-tts defaults to SentenceBoundary.
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, boundary="WordBoundary")
    boundaries: list[WordBoundary] = []
    # Streaming write of audio chunks; a plain file handle is appropriate here.
    with open(out_path, "wb") as fh:  # noqa: ASYNC230
        async for chunk in communicate.stream():
            ctype = chunk["type"]
            if ctype == "audio":
                fh.write(chunk["data"])
            elif ctype in ("WordBoundary", "SentenceBoundary"):
                start = chunk["offset"] / 1e7           # 100-ns ticks -> seconds
                dur = chunk["duration"] / 1e7
                boundaries.append(WordBoundary(text=chunk["text"], start=start, end=start + dur))
    return boundaries


def _edge_tts(text: str, voice: str, rate: float, out_path: Path) -> list[WordBoundary]:
    return asyncio.run(_edge_synthesize(text, voice, _rate_to_edge(rate), out_path))


def _openai_tts(text: str, voice: str, out_path: Path) -> list[WordBoundary]:
    from openai import OpenAI

    cfg = get_settings().llm.openai
    if not cfg.api_key:
        raise RuntimeError("OpenAI API key is not configured for TTS.")
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url or None)
    # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
    openai_voice = voice if voice in {"alloy", "echo", "fable", "onyx", "nova", "shimmer"} else "alloy"
    with client.audio.speech.with_streaming_response.create(
        model="tts-1", voice=openai_voice, input=text
    ) as resp:
        resp.stream_to_file(str(out_path))
    return []  # no word timings


def _audio_duration(path: Path) -> float:
    from moviepy import AudioFileClip

    clip = AudioFileClip(str(path))
    try:
        return float(clip.duration)
    finally:
        clip.close()


def synthesize(text: str, out_dir: Path, voice: str | None = None, rate: float = 1.0) -> VoiceResult:
    """Generate a voiceover audio file and return it with timing metadata."""
    settings = get_settings()
    provider = settings.tts.provider.lower()
    voice = voice or settings.tts.default_voice
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "voice.mp3"

    logger.info(f"Synthesizing voiceover with {provider} / {voice}")
    if provider == "edge":
        boundaries = _edge_tts(text, voice, rate, out_path)
    elif provider == "openai":
        boundaries = _openai_tts(text, voice, out_path)
    else:
        raise ValueError(f"Unknown TTS provider: {provider!r}")

    duration = _audio_duration(out_path)
    logger.info(f"Voiceover duration: {duration:.2f}s, {len(boundaries)} word boundaries")
    return VoiceResult(audio_path=out_path, duration=duration, boundaries=boundaries)
