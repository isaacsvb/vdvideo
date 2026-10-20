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
├─ resources/songs/  # drop your .mp3 background tracks here
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
# POST /videos  {"topic": "the benefits of reading", "aspect_ratio": "9:16"}
# GET  /tasks/{id}            → progress
# GET  /tasks/{id}/download   → MP4
```

**CLI**
```bash
python main.py "the benefits of reading"
python main.py "space exploration" --aspect 16:9 --voice en-US-GuyNeural
```

## Notes

- **Subtitles** are rendered by moviepy's `TextClip`, which needs **ImageMagick**
  installed on the system. If it's missing, video still renders — just without
  burned-in captions (the `.srt` file is still produced in the task folder).
- Output and intermediate files go under `storage/` (gitignored).
- Respect the licences of any stock footage and music you use.
