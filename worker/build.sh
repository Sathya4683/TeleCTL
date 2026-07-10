#!/usr/bin/env bash
# Build the worker release tarball.
#
# Two output artifacts in /out:
#   worker.tar.gz       self-contained Python + worker package
#   worker.tar.gz.sha256
#
# Called by CI; safe to run locally with Docker installed.
#
# Usage: scripts/build_worker.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "[build_worker] Building worker release tarball via Docker..."

docker build -t wactl-worker-builder -f worker/Dockerfile .
mkdir -p dist
docker create --name wactl-worker-extract wactl-worker-builder /bin/true >/dev/null
docker cp wactl-worker-extract:/worker.tar.gz dist/worker.tar.gz
docker cp wactl-worker-extract:/worker.tar.gz.sha256 dist/worker.tar.gz.sha256
docker rm wactl-worker-extract >/dev/null

echo "[build_worker] Built dist/worker.tar.gz ($(du -h dist/worker.tar.gz | cut -f1))"
sha256sum -c dist/worker.tar.gz.sha256
