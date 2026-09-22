FROM python:3.12-slim

# ffmpeg is required by yt-dlp to merge 1080p video+audio and to extract MP3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

# Render provides $PORT; the app binds to it in webhook mode.
CMD ["python", "-m", "bot.main"]
