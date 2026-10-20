# 🎬 vdvideo

An all-in-one **AI short-video generator**. Give it a topic or keyword and it
writes the script, finds free stock footage, generates a voiceover, burns in
subtitles, adds background music, and renders a finished HD short video —
vertical (9:16) for TikTok / Shorts / Reels or horizontal (16:9) for YouTube.

> Inspired by the architecture of
> [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo).
> Content was rephrased for compliance with licensing restrictions.

## Pipeline

```
topic → LLM (script + search terms) → stock footage (Pexels/Pixabay)
      → TTS voiceover (edge-tts) → subtitles (.srt) → background music
      → FFmpeg/moviepy compose → final MP4 (9:16 or 16:9)
```

## Features

- **Pluggable LLM** for script generation — OpenAI or Google Gemini.
- **Free stock footage** from Pexels (default) or Pixabay.
- **Free TTS** via `edge-tts` (no API key, many voices) with word-accurate
  subtitle timings; optional OpenAI TTS.
- **Customizable** voice, speaking rate, subtitle style/position, and music volume.
- **Both formats:** 1080×1920 (9:16) and 1920×1080 (16:9).
- **Auto-upload to YouTube** via the official Data API v3 (OAuth) — stable,
  no fragile browser automation.
- **Scheduler** to generate (and optionally publish) videos at a future time.
- **Three interfaces:** Streamlit web UI, FastAPI REST API, and a CLI.
- **Bundled FFmpeg** via `imageio-ffmpeg` — no system install required.

## Project layout

```
vdvideo/
├─ app/
│  ├─ config/        # settings from config.toml + env vars
│  ├─ models/        # Pydantic schemas (VideoParams, TaskStatus, …)
│  ├─ services/      # llm, material, voice, subtitle, video
│  ├─ router/        # FastAPI app
│  ├─ util/          # ffmpeg wiring, music helpers
│  └─ task.py        # pipeline orchestration + progress
├─ webui/Main.py     # Streamlit UI
├─ main.py           # CLI
├─ scripts/
│  └─ generate_music.py   # synthesize royalty-free background tracks
├─ resources/songs/       # bundled + user-provided .mp3 tracks
├─ tests/                 # pytest suite
├─ Dockerfile
├─ docker-compose.yml
├─ config.example.toml
└─ requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp config.example.toml config.toml  # then add your API keys
```

### Run with Docker (recommended — bundles ffmpeg + ImageMagick)

The Docker image installs `ffmpeg` and `ImageMagick` (with a relaxed policy so
burned-in subtitles work out of the box) and generates the bundled music at
build time.

```bash
# Put your keys in a .env file (OPENAI_API_KEY, PEXELS_API_KEY, ...)
docker compose up --build
# UI  → http://localhost:8501
# API → http://localhost:8000
```

### Configuration

Set keys in `config.toml` **or** via environment variables (env vars win):

| Setting | config.toml | Env var |
|---|---|---|
| OpenAI key | `[llm.openai] api_key` | `OPENAI_API_KEY` |
| Gemini key | `[llm.gemini] api_key` | `GEMINI_API_KEY` |
| Pexels key | `[material.pexels] api_key` | `PEXELS_API_KEY` |
| LLM provider | `[llm] provider` | `LLM_PROVIDER` |
| Footage provider | `[material] provider` | `MATERIAL_PROVIDER` |

- Pexels API key (free): https://www.pexels.com/api/
- `config.toml` and `.env` are gitignored — secrets never get committed.

## Usage

**Web UI**
```bash
streamlit run webui/Main.py
```

**REST API**
```bash
uvicorn app.router.api:app --reload
# POST /videos   {"topic": "the benefits of reading", "aspect_ratio": "9:16"}
#                optional: add "upload": {"enabled": true, "privacy_status": "unlisted"}
# GET  /tasks/{id}            → progress (includes youtube_video_id once uploaded)
# GET  /tasks/{id}/download   → MP4
# POST /schedule  {"topic": "...", "run_at": "2026-01-01T12:00:00Z", "upload": {...}}
# GET  /schedule              → list scheduled jobs
# DELETE /schedule/{job_id}   → cancel a scheduled job
```

**CLI**
```bash
python main.py "the benefits of reading"
python main.py "space exploration" --aspect 16:9 --voice en-US-GuyNeural
```

## Publishing to YouTube

Finished videos can be uploaded automatically via the **official YouTube Data
API v3** (OAuth) — chosen over browser automation because it's stable and
supported.

1. In Google Cloud Console, enable **YouTube Data API v3** and create an OAuth
   **Desktop app** credential; download the client-secrets JSON.
2. Set `[youtube] client_secrets_file` (or `YOUTUBE_CLIENT_SECRETS_FILE`).
3. Enable "Upload to YouTube" in the UI, or send an `upload` block to the API.
   The first upload opens a browser once to authorize; the token is then cached.

## Scheduling

Queue a job to run later (the "post on a schedule" workflow): `POST /schedule`
with a `run_at` timestamp. A lightweight background thread (started with the API)
runs due jobs and persists them to `storage/schedule.json`, so they survive
restarts. Each job can include the same `upload` block to publish on completion.

## Background music

Three royalty-free ambient tracks are **synthesized from scratch** (no licensing
restrictions) and ship in `resources/songs/`. Regenerate or extend them with:

```bash
python scripts/generate_music.py
```

Drop your own royalty-free `.mp3` files into `resources/songs/` and they appear
automatically in the UI / CLI. Pick a track with `--bgm-name <file.mp3>` and set
its level with `--bgm-volume` (or the UI slider).

## Tests

```bash
pip install -r requirements.txt   # includes pytest
pytest
```

The suite covers the deterministic logic — schema validation, aspect-ratio
dimensions, subtitle `.srt` building/grouping/timing, config/env precedence,
LLM parsing & provider routing (mocked), and the music/ffmpeg helpers — with all
external services mocked so no API keys or network are required.

## Notes

- **Subtitles** are rendered by moviepy's `TextClip`, which needs **ImageMagick**.
  The Docker image installs and configures it for you. For a local (non-Docker)
  run without ImageMagick, the video still renders — just without burned-in
  captions (the `.srt` file is still produced in the task folder).
- Output and intermediate files go under `storage/` (gitignored).
- Respect the licences of any stock footage and music you use.
