# syntax=docker/dockerfile:1.4
#
# openfilter-base — a fresh-OS Python base shared by openfilter images (the built-in
# filter images here, and standalone filter repos alike).
#
# Its whole job is to be a `python:X-slim` with every outstanding Debian security update
# already applied (apt upgrade). Downstream images inherit a patched OS from ONE place
# instead of each pinning a stale `python:X.Y.Z-slim` that silently drifts behind Debian's
# point releases (openssl, gnutls, the python apt package, …). Rebuilt on a weekly schedule
# so the OS stays current.
#
# Deliberately MINIMAL: no system libraries are installed here. Each filter installs only
# the libraries IT actually needs (e.g. libzbar0 for QR decoding) in its own Dockerfile, so
# the shared base stays small and no filter inherits a library — and its CVEs — it never
# uses. (The built-in video filters need nothing extra: OpenCV is headless and PyAV bundles
# its own ffmpeg, so no system ffmpeg/libGL/X11 is required.)
#
# Published per supported Python version: plainsightai/openfilter-base:py3.10 .. py3.14
# (openfilter's requires-python is >=3.10,<3.15). Consumers pick the tag for their version:
#   FROM plainsightai/openfilter-base:py3.11
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim

# The one thing this image does: apply all outstanding Debian security patches on top of
# the python base. That clears the OS-package CVEs (openssl/libssl3, gnutls, python) that
# every filter inherits from a stale python:X.Y.Z-slim pin.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Standard non-root runtime layout shared by openfilter images. USER is deliberately NOT
# set here: downstream images COPY build artifacts in as root and switch to appuser at the
# end, so flipping the user is the consumer's last step.
RUN useradd -ms /bin/bash appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
WORKDIR /app
