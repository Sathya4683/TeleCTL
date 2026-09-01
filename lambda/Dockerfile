# syntax=docker/dockerfile:1.7
# Build the webhook Lambda as a container image.
#
# We use a container image instead of a zipped deployment because
# ``pdf2docx`` pulls in opencv-python-headless (~80 MB) and pymupdf
# (~60 MB), which doesn't fit under Lambda's 50 MB zipped limit.
# Container images allow up to 10 GB.
#
# The final image uses AWS's official Python 3.12 Lambda base image,
# which ships the Lambda Runtime Interface Emulator. CMD points at
# the handler module path.
#
# Usage:
#   docker build -t wactl-webhook:latest -f lambda/Dockerfile .
#   docker push <ecr-url>:latest

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Copy only the files needed to resolve deps. README.md is intentionally
# excluded — uv export --no-emit-project skips the local wactl package
# so the README is never read.
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY lambda ./lambda

RUN pip install --no-cache-dir uv && \
    uv export --frozen --no-hashes --no-dev --no-emit-project \
        --format requirements-txt > /tmp/requirements.txt && \
    uv pip install --python /usr/local/bin/python --target /out \
        --no-cache --no-compile-bytecode -r /tmp/requirements.txt

# Copy our package on top of the deps. ``--no-emit-project`` above
# already excluded it from the requirements file.
RUN cp -r /build/src/wactl /out/wactl \
    && cp -r /build/lambda /out/lambda

# ──────────────────────────────────────────────────────────────────────
# Final image: AWS Lambda Python 3.12 base image. Already contains the
# Lambda Runtime Interface Emulator; we just need our code on the path.
# Image is x86_64 to match the architectures field in infra/lambda.tf.
FROM public.ecr.aws/lambda/python:3.12-x86_64

WORKDIR /var/task

COPY --from=builder /out /var/task

# CMD points at the handler module path; the Lambda runtime imports
# ``lambda_function`` from it and calls ``lambda_handler(event, context)``.
CMD ["lambda.webhook.handler.lambda_handler"]

