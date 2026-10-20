"""Shared pytest fixtures and path setup."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_out(tmp_path: Path) -> Path:
    """A temporary output directory for tests that write files."""
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def word_boundaries():
    """A small set of word boundaries mimicking edge-tts output."""
    from app.services.voice import WordBoundary

    words = ["Reading", "expands", "your", "mind", "and", "vocabulary", "every", "single", "day"]
    out = []
    t = 0.0
    for w in words:
        out.append(WordBoundary(text=w, start=t, end=t + 0.4))
        t += 0.45
    return out
