# syntax=docker/dockerfile:1.4
#
# Same image as the published filter images, built from THIS checkout instead of the
# released wheel on PyPI, so a change can be run before it is tagged. Build context is
# the repo root:
#
#   docker build -f docker/dev.Dockerfile -t plainsightai/openfilter-webvis:dev .
#
# FILTER selects which built-in filter the image runs (webvis, video_in, ...), so one
# Dockerfile covers the whole pipeline rather than one -dev file per filter.
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev && rm -rf /var/lib/apt/lists/*

COPY . /src
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "/src[all]"

FROM plainsightai/openfilter-base:py3.14

USER appuser

COPY --from=builder /usr/local /usr/local

ENV FILTER=webvis
CMD ["sh", "-c", "python -m openfilter.filter_runtime.filters.$FILTER"]
