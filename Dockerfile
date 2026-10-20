# vdvideo — AI short-video generator
FROM python:3.11-slim

# System dependencies:
#   ffmpeg       — video/audio encoding
#   imagemagick  — required by moviepy's TextClip to burn in subtitles
#   fonts        — a sane default font for subtitles
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        imagemagick \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ImageMagick's default policy on Debian blocks the TEXT/LABEL/@path operations
# that moviepy's TextClip relies on. Relax those entries so subtitles render.
# Matches the real Debian policy.xml entries:
#   <policy domain="coder" rights="none" pattern="TEXT" />
#   <policy domain="coder" rights="none" pattern="LABEL" />
#   <policy domain="path"  rights="none" pattern="@*" />
RUN set -eux; \
    for policy in /etc/ImageMagick-6/policy.xml /etc/ImageMagick-7/policy.xml; do \
        if [ -f "$policy" ]; then \
            sed -ri 's|(domain="coder" rights=")none("[[:space:]]+pattern="TEXT")|\1read\|write\2|' "$policy"; \
            sed -ri 's|(domain="coder" rights=")none("[[:space:]]+pattern="LABEL")|\1read\|write\2|' "$policy"; \
            sed -ri '/domain="path"[[:space:]]+rights="none"[[:space:]]+pattern="@\*"/d' "$policy"; \
        fi; \
    done

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate the bundled royalty-free background tracks at build time.
RUN python scripts/generate_music.py || true

# Streamlit (8501) and FastAPI (8000)
EXPOSE 8501 8000

# Default: launch the web UI. Override `command` to run the API or CLI.
CMD ["streamlit", "run", "webui/Main.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true"]
