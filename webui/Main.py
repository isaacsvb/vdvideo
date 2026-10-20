"""vdvideo — Streamlit web UI.

Run with:  streamlit run webui/Main.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

# Make the project importable when run via `streamlit run`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.models import (
    AspectRatio,
    SubtitlePosition,
    SubtitleStyle,
    TaskState,
    UploadParams,
    VideoParams,
)
from app.task import get_task, run_pipeline_async
from app.util.media import list_songs

SONGS_DIR = PROJECT_ROOT / "resources" / "songs"

st.set_page_config(page_title="vdvideo", page_icon="🎬", layout="wide")
st.title("🎬 vdvideo — AI Short Video Generator")
st.caption("Give a topic; get a finished short video with script, footage, voiceover, subtitles & music.")

settings = get_settings()

# --------------------------------------------------------------------------- #
# Sidebar: config status
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Configuration")
    st.write(f"**LLM provider:** `{settings.llm.provider}`")
    st.write(f"**Footage provider:** `{settings.material.provider}`")
    st.write(f"**TTS provider:** `{settings.tts.provider}`")

    def _ok(flag: bool) -> str:
        return "✅" if flag else "❌ missing"

    st.divider()
    st.subheader("API keys")
    st.write(f"OpenAI: {_ok(bool(settings.llm.openai.api_key))}")
    st.write(f"Gemini: {_ok(bool(settings.llm.gemini.api_key))}")
    st.write(f"Pexels: {_ok(bool(settings.material.pexels.api_key))}")
    st.caption("Set keys in `config.toml` or via environment variables, then restart.")

# --------------------------------------------------------------------------- #
# Main form
# --------------------------------------------------------------------------- #
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Content")
    topic = st.text_input("Topic or keyword", placeholder="e.g. the benefits of reading")
    language = st.selectbox("Language", ["en", "es", "fr", "de", "pt", "it"], index=0)
    paragraphs = st.slider("Script length (sentences)", 1, 8, 3)
    aspect = st.radio(
        "Format",
        [AspectRatio.PORTRAIT, AspectRatio.LANDSCAPE],
        format_func=lambda a: f"{a.value}  ({'vertical' if a is AspectRatio.PORTRAIT else 'horizontal'} HD)",
        horizontal=True,
    )
    max_duration = st.slider("Max duration (seconds)", 10, 180, 60, step=5)

with col_right:
    st.subheader("Voice")
    voice_name = st.text_input("Voice (edge-tts short name)", value=settings.tts.default_voice)
    voice_rate = st.slider("Speaking rate", 0.5, 2.0, 1.0, step=0.05)
    voice_volume = st.slider("Voiceover volume", 0.0, 1.0, 1.0, step=0.05)

    st.subheader("Subtitles")
    subs_enabled = st.checkbox("Burn in subtitles", value=True)
    sub_cols = st.columns(2)
    with sub_cols[0]:
        sub_font = st.slider("Font size", 24, 120, 72, step=2)
        sub_color = st.color_picker("Text color", "#FFFFFF")
    with sub_cols[1]:
        sub_position = st.selectbox("Position", list(SubtitlePosition), index=2, format_func=lambda p: p.value)
        sub_stroke = st.color_picker("Outline color", "#000000")

    st.subheader("Music")
    songs = list_songs(SONGS_DIR)
    bgm_enabled = st.checkbox("Add background music", value=bool(songs))
    bgm_name = st.selectbox("Track", songs, index=0) if songs else None
    if not songs:
        st.caption("No music found. Drop .mp3 files into `resources/songs/`.")
    bgm_volume = st.slider("Music volume", 0.0, 1.0, 0.15, step=0.01)

    st.subheader("Publish to YouTube")
    yt_configured = bool(settings.youtube.client_secrets_file)
    upload_enabled = st.checkbox(
        "Upload to YouTube when done", value=False, disabled=not yt_configured
    )
    if not yt_configured:
        st.caption("Configure `[youtube] client_secrets_file` to enable uploads.")
    yt_title = st.text_input("Video title (defaults to topic)", value="", disabled=not upload_enabled)
    yt_privacy = st.selectbox(
        "Privacy", ["private", "unlisted", "public"], index=0, disabled=not upload_enabled
    )

st.divider()
generate = st.button("🚀 Generate video", type="primary", use_container_width=True, disabled=not topic)

if generate and topic:
    params = VideoParams(
        topic=topic,
        language=language,
        paragraphs=paragraphs,
        aspect_ratio=aspect,
        max_duration=max_duration,
        voice=voice_name or None,
        voice_rate=voice_rate,
        voice_volume=voice_volume,
        subtitles=SubtitleStyle(
            enabled=subs_enabled,
            font_size=sub_font,
            color=sub_color,
            stroke_color=sub_stroke,
            position=sub_position,
        ),
        bgm_enabled=bgm_enabled,
        bgm_name=bgm_name,
        bgm_volume=bgm_volume,
    )
    upload = UploadParams(
        enabled=upload_enabled,
        title=yt_title or None,
        privacy_status=yt_privacy,
    ) if upload_enabled else None
    st.session_state["task_id"] = run_pipeline_async(params, upload=upload)

# --------------------------------------------------------------------------- #
# Progress / result
# --------------------------------------------------------------------------- #
task_id = st.session_state.get("task_id")
if task_id:
    st.subheader("Progress")
    bar = st.progress(0)
    status_box = st.empty()
    while True:
        status = get_task(task_id)
        if status is None:
            status_box.warning("Task not found.")
            break
        bar.progress(status.progress)
        status_box.write(f"**{status.state.value}** — {status.message}")
        if status.state in (TaskState.SUCCEEDED, TaskState.FAILED):
            break
        time.sleep(1.0)

    status = get_task(task_id)
    if status and status.state is TaskState.SUCCEEDED and status.video_path:
        st.success("Video ready!")
        video_bytes = Path(status.video_path).read_bytes()
        st.video(video_bytes)
        st.download_button("⬇️ Download MP4", video_bytes, file_name=f"{task_id}.mp4", mime="video/mp4")
        if status.youtube_video_id:
            st.markdown(f"📺 **Uploaded to YouTube:** https://youtu.be/{status.youtube_video_id}")
    elif status and status.state is TaskState.FAILED:
        st.error(f"Generation failed: {status.error}")
