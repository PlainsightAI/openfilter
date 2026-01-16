# syntax=docker/dockerfile:1.4
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev && rm -rf /var/lib/apt/lists/*

ARG VERSION
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "openfilter[image_out]==${VERSION}"

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd -ms /bin/bash appuser

WORKDIR /app
RUN mkdir -p /app/logs && chown -R appuser:appuser /app
USER appuser

COPY --from=builder /usr/local /usr/local

CMD ["python", "-m", "openfilter.filter_runtime.filters.image_out"]
