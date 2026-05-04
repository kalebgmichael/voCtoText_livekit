# syntax=docker/dockerfile:1.5
FROM python:3.10-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install faster-whisper fastapi uvicorn python-multipart

COPY server.py /app/server.py
WORKDIR /app
EXPOSE 80

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80"]
