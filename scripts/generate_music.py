"""Generate royalty-free background music tracks.

These tracks are synthesized from scratch (simple ambient chord pads), so they
carry **no licensing restrictions** — you are free to use them in your videos.

Run:
    python scripts/generate_music.py
Output goes to resources/songs/*.mp3 and the files are picked up automatically
by the web UI and CLI.

Requires numpy (in requirements.txt) and the bundled ffmpeg (imageio-ffmpeg).
"""
from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SONGS_DIR = PROJECT_ROOT / "resources" / "songs"
SAMPLE_RATE = 44100

# Each track: name, list of chords (each chord = tuple of note frequencies in Hz),
# seconds per chord, and a subtle tempo for an amplitude "breathing" effect.
TRACKS: dict[str, dict] = {
    "ambient_calm.mp3": {
        "chords": [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66),
                   (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)],
        "chord_seconds": 4.0,
        "breath_hz": 0.12,
    },
    "uplifting_pad.mp3": {
        "chords": [(261.63, 329.63, 392.0), (293.66, 369.99, 440.0),
                   (329.63, 415.30, 493.88), (293.66, 369.99, 440.0)],
        "chord_seconds": 3.5,
        "breath_hz": 0.18,
    },
    "lofi_mellow.mp3": {
        "chords": [(146.83, 185.0, 220.0), (164.81, 207.65, 246.94),
                   (130.81, 164.81, 196.0), (155.56, 196.0, 233.08)],
        "chord_seconds": 4.5,
        "breath_hz": 0.10,
    },
}

TOTAL_SECONDS = 32.0  # loopable length; app loops it to the video duration


def _adsr(n: int, attack: float = 0.25, release: float = 0.4) -> np.ndarray:
    """A soft attack/release envelope so chords fade in and out smoothly."""
    env = np.ones(n)
    a = int(n * attack)
    r = int(n * release)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] = np.linspace(1, 0, r)
    return env


def _chord_wave(freqs: tuple[float, ...], seconds: float) -> np.ndarray:
    n = int(SAMPLE_RATE * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    wave_sum = np.zeros(n)
    for f in freqs:
        # Fundamental + a soft octave + a touch of fifth for warmth.
        wave_sum += np.sin(2 * math.pi * f * t)
        wave_sum += 0.35 * np.sin(2 * math.pi * (f * 2) * t)
        wave_sum += 0.18 * np.sin(2 * math.pi * (f * 1.5) * t)
    wave_sum /= len(freqs) * 1.5
    return wave_sum * _adsr(n)


def _build_track(spec: dict) -> np.ndarray:
    chords = spec["chords"]
    chord_seconds = spec["chord_seconds"]
    samples: list[np.ndarray] = []
    elapsed = 0.0
    i = 0
    while elapsed < TOTAL_SECONDS:
        freqs = chords[i % len(chords)]
        samples.append(_chord_wave(freqs, chord_seconds))
        elapsed += chord_seconds
        i += 1
    track = np.concatenate(samples)[: int(SAMPLE_RATE * TOTAL_SECONDS)]

    # Slow amplitude "breathing" for a living, ambient feel.
    t = np.linspace(0, TOTAL_SECONDS, track.size, endpoint=False)
    breath = 0.85 + 0.15 * np.sin(2 * math.pi * spec["breath_hz"] * t)
    track *= breath

    # Normalize and apply a gentle headroom so the mix never clips.
    peak = np.max(np.abs(track)) or 1.0
    return (track / peak) * 0.6


def _write_mp3(samples: np.ndarray, out_path: Path) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pcm = np.int16(np.clip(samples, -1.0, 1.0) * 32767)

    tmp_wav = out_path.with_suffix(".tmp.wav")
    with wave.open(str(tmp_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    subprocess.run(
        [ffmpeg, "-y", "-i", str(tmp_wav), "-codec:a", "libmp3lame", "-b:a", "128k", str(out_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp_wav.unlink(missing_ok=True)


def main() -> int:
    SONGS_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in TRACKS.items():
        out = SONGS_DIR / name
        print(f"Generating {name} ...")
        samples = _build_track(spec)
        _write_mp3(samples, out)
        print(f"  -> {out} ({out.stat().st_size // 1024} KB)")
    print(f"\nDone. {len(TRACKS)} royalty-free tracks in {SONGS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
