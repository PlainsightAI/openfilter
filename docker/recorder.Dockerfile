# syntax=docker/dockerfile:1.4
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev && rm -rf /var/lib/apt/lists/*

ARG VERSION
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "openfilter[recorder]==${VERSION}"

FROM plainsightai/openfilter-base:py3.13

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb1 libxcb-shm0 libxcb-render0 libx11-6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

USER appuser

COPY --from=builder /usr/local /usr/local

CMD ["python", "-m", "openfilter.filter_runtime.filters.recorder"]
