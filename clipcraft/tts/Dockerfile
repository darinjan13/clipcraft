FROM python:3.11.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    espeak-ng \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tts/requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/models && \
    curl -sL -o /app/models/en_US-lessac-medium.onnx \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx && \
    curl -sL -o /app/models/en_US-lessac-medium.onnx.json \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

COPY tts/server.py /app/server.py
COPY tts/audio_utils.py /app/audio_utils.py

RUN mkdir -p /data/jobs && chmod 777 /data/jobs

ENV PIPER_MODEL=/app/models/en_US-lessac-medium.onnx

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "300", "--preload", "server:app"]
