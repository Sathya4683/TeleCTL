# syntax=docker/dockerfile:1.7
# Build stage for the worker release tarball. The artifact is consumed by
# the EC2 user-data script, which downloads it from S3 and extracts to
# /opt/wactl/. Keeping a Dockerfile (rather than just a bash script) makes
# the contract transparent and inspectable in CI.

FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /src

# System deps required to build wheels for our Python packages.
# - libffi-dev, zlib1g-dev: Pillow + pymupdf wheels.
# - ffmpeg: pydub uses ffmpeg for WAV→MP3 export (audiobook pipeline).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        zlib1g-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy source + dependency spec.
# (README.md is intentionally excluded — ``uv export --no-emit-project``
# below never tries to install the local wactl package, so the README
# is unnecessary at build time. We copy wactl in manually after.)
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY worker ./worker

# Install uv (modern pip replacement) and use it to build a self-contained
# package set: every dependency is installed under /out/packages, suitable
# for bundling into a release tarball.
#
# ``--no-emit-project`` excludes the local ``wactl`` package from the
# requirements file — we copy it in manually below instead of letting uv
# try to build it from this directory (avoids needing README.md at build
# time and keeps the layer cache friendly).
RUN pip install --no-cache-dir uv && \
    uv export --frozen --no-hashes --no-emit-project --format requirements-txt > /tmp/requirements.txt && \
    uv pip install --python /usr/local/bin/python --target /out/packages \
        --no-cache --no-compile-bytecode -r /tmp/requirements.txt

# Copy the in-tree package + worker entry point on top of the deps.
RUN cp -r /src/src/wactl /out/packages/wactl && \
    cp -r /src/worker /out/worker

# Bundle as a single tarball for delivery.
WORKDIR /out
RUN tar --owner=0 --group=0 -czf /out/worker.tar.gz packages worker && \
    sha256sum worker.tar.gz > worker.tar.gz.sha256

# Final stage: a tiny image whose only job is to hold the artifact.
FROM scratch AS artifact
COPY --from=builder /out/worker.tar.gz /worker.tar.gz
COPY --from=builder /out/worker.tar.gz.sha256 /worker.tar.gz.sha256
