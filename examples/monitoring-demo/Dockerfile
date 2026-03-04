# syntax=docker/dockerfile:1.4
# Build openfilter from local source for Docker-based pipeline testing.
# Build context must be the repo root: docker build -f Dockerfile ../..
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev && rm -rf /var/lib/apt/lists/*

COPY . /src
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "/src[all]"

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libxcb1 libxcb-shm0 libxcb-render0 libx11-6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash appuser

WORKDIR /app
RUN mkdir -p /app/logs && chown -R appuser:appuser /app
USER appuser

COPY --from=builder /usr/local /usr/local
COPY examples/monitoring-demo/timing_filter /app/timing_filter
COPY examples/monitoring-demo/filters /app/filters

CMD ["python", "-m", "openfilter.filter_runtime.filters.video_in"]
