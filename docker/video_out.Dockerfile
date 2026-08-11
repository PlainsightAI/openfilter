# syntax=docker/dockerfile:1.4
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev && rm -rf /var/lib/apt/lists/*

ARG VERSION
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "openfilter[video_out]==${VERSION}"

FROM plainsightai/openfilter-base:py3.14

USER appuser

COPY --from=builder /usr/local /usr/local

CMD ["python", "-m", "openfilter.filter_runtime.filters.video_out"]
