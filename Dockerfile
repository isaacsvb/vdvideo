# vdvideo — AI short-video generator
FROM python:3.12-slim

# System dependencies:
#   ffmpeg — video/audio encoding
# NOTE: moviepy 2.x renders subtitles via Pillow, so ImageMagick is no longer
# needed. A TTF font is bundled with the project (resources/fonts), so no
# system fonts are required either.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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
