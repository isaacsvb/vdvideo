"""Subtitle service: build an .srt file from TTS word boundaries.

Groups words into short, readable caption lines (good for vertical video) and
times each line from the TTS word boundaries. When no boundaries are available
(e.g. OpenAI TTS), falls back to splitting the audio duration evenly.
"""
from __future__ import annotations

from pathlib import Path

from app.services.voice import WordBoundary

_MAX_CHARS_PER_LINE = 36
_MAX_WORDS_PER_LINE = 7


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _group_boundaries(boundaries: list[WordBoundary]) -> list[tuple[float, float, str]]:
    lines: list[tuple[float, float, str]] = []
    cur: list[WordBoundary] = []

    def flush() -> None:
        if cur:
            text = " ".join(w.text for w in cur)
            lines.append((cur[0].start, cur[-1].end, text))

    char_count = 0
    for w in boundaries:
        prospective = char_count + len(w.text) + 1
        if cur and (len(cur) >= _MAX_WORDS_PER_LINE or prospective > _MAX_CHARS_PER_LINE):
            flush()
            cur, char_count = [], 0
        cur.append(w)
        char_count += len(w.text) + 1
    flush()
    return lines


def _even_split(text: str, duration: float) -> list[tuple[float, float, str]]:
    words = text.split()
    if not words:
        return []
    # Chunk words into caption-sized lines.
    chunks: list[list[str]] = []
    cur: list[str] = []
    char_count = 0
    for word in words:
        if cur and (len(cur) >= _MAX_WORDS_PER_LINE or char_count + len(word) + 1 > _MAX_CHARS_PER_LINE):
            chunks.append(cur)
            cur, char_count = [], 0
        cur.append(word)
        char_count += len(word) + 1
    if cur:
        chunks.append(cur)

    total_words = len(words)
    lines: list[tuple[float, float, str]] = []
    elapsed = 0.0
    for chunk in chunks:
        share = duration * (len(chunk) / total_words)
        lines.append((elapsed, elapsed + share, " ".join(chunk)))
        elapsed += share
    return lines


def build_srt(
    text: str,
    duration: float,
    boundaries: list[WordBoundary],
    out_dir: Path,
) -> Path | None:
    """Write subtitles.srt and return its path (or None if no text)."""
    lines = _group_boundaries(boundaries) if boundaries else _even_split(text, duration)
    if not lines:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    srt_path = out_dir / "subtitles.srt"
    with open(srt_path, "w", encoding="utf-8") as fh:
        fh.writelines(f"{i}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{content}\n\n" for i, (start, end, content) in enumerate(lines, 1))
    return srt_path
