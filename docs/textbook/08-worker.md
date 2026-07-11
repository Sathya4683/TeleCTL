# 08 — The Worker: Long-polling, Dispatch, Shutdown

The Lambda is the front door. The worker is the back office. Anything too slow to run inside a 15-minute Lambda budget lands here, in a single always-on process that drains a queue.

This chapter covers what the worker is, how it runs, how it shuts down gracefully, and how its code is built and deployed.

## 8.1 — Why a worker at all?

Lambda is billed per millisecond. Lambda also has a 15-minute max execution time. Both numbers matter:

| Command | Typical runtime | Lambda cost per invocation | Worker cost per invocation |
|---|---|---|---|
| `/image-resize` | 1–2s | ~$0.000033 | n/a (sync) |
| `/image-compress` | 1–2s | ~$0.000033 | n/a (sync) |
| `/web-summary` | 5–15s | ~$0.000200 | n/a (sync) |
| `/github-pr` | 5–10s | ~$0.000170 | n/a (sync) |
| `/translate` | 2–5s | ~$0.000085 | n/a (sync) |
| `/pdf-docx` | 5–30s | expensive | cheap |
| `/pdf-audio` | 30–120s | very expensive | cheap |
| `/merge-pdf` | 5–30s | expensive | cheap |
| `/split-pdf` | 5–20s | expensive | cheap |

The async commands would *fit* inside Lambda's 15-minute ceiling, but they'd cost 10–100× more than running on a cheap EC2 instance. So we have one `t4g.nano` (free tier, $0 if you stay within 750 hours/month) that polls SQS and runs the slow commands.

A second benefit: **the user gets a fast 200 OK.** The Lambda just enqueues and returns in ~100ms. Meta doesn't retry. The worker takes 5–60 seconds to actually process, but the user sees a "queued…" reply immediately.

## 8.2 — The file layout

```
worker/
├── __init__.py
├── main.py                    # the long-poll + dispatch loop
├── shutdown.py                # SIGTERM/SIGINT handlers
├── build.sh                   # the Docker build entry point
├── Dockerfile                 # the build recipe
└── systemd/
    └── wactl-worker.service   # the systemd unit file
```

The `worker/` directory is *outside* the `src/wactl/` package. The worker is a separate deployable that imports from `wactl` (the shared code) but has its own entry point.

## 8.3 — The main loop

`worker/main.py` is the entry point. The whole thing is a `while not shutdown.is_set()` loop:

```python
class Worker:
    async def run(self) -> None:
        shutdown.install()
        logger.info("worker.starting")
        try:
            while not shutdown.is_set():
                try:
                    await self._poll_once()
                except Exception as exc:
                    logger.error("worker.poll_failed", ...)
                    await asyncio.sleep(min(5, settings.http_timeout_seconds))
        finally:
            logger.info("worker.stopped")
            reset_context()
```

Three things to notice:

1. **Signal handlers are installed once at the top.** `shutdown.install()` registers `SIGTERM` and `SIGINT` to set an `asyncio.Event`.
2. **The loop is one-poll-per-iteration.** Each call to `_poll_once()` either processes a batch of messages or returns immediately on an empty queue. The 20-second long-poll timeout (configured in `_poll_once`) is the natural rate limit.
3. **Exceptions don't kill the process.** A network blip or a SQS hiccup is logged and slept (≤5s) before retrying. systemd will restart the process if it does die.

## 8.4 — The poll cycle

```python
async def _poll_once(self) -> None:
    queue_url = settings.sqs_jobs_queue_url
    if not queue_url:
        logger.warning("worker.no_queue_url")
        await asyncio.sleep(5)
        return

    messages = await asyncio.to_thread(
        sqs.receive_message,
        queue_url,
        max_messages=10,
        wait_seconds=20,
        visibility_timeout=900,
    )
    if not messages:
        return
    for message in messages:
        await self._process_message(message)
```

The `sqs.receive_message` is a **blocking** call (it does I/O over the network). To not stall the asyncio event loop, we run it in `asyncio.to_thread` — that pushes the blocking call onto a thread-pool worker, leaving the event loop free to handle signals.

The parameters:
- `max_messages=10` — receive up to 10 in one batch. SQS caps at 10 anyway.
- `wait_seconds=20` — long polling. If no messages, SQS holds the connection open for up to 20s before returning empty. This avoids the "thundering herd" of polling every second.
- `visibility_timeout=900` — 15 minutes. Once a message is received, it's invisible to other consumers for 15 minutes. If we don't `delete_message` it by then, it reappears for another consumer to try.

## 8.5 — Message processing

```python
async def _process_message(self, message: dict[str, Any]) -> None:
    handle = message.get("_receipt_handle")
    body = message.get("job")
    if not isinstance(body, str):
        logger.warning("worker.unparseable_message", keys=list(message.keys()))
        if handle:
            await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
        return

    try:
        job = Job.model_validate_json(body)
    except Exception as exc:
        logger.error("worker.job_parse_failed", ...)
        if handle:
            await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
        return

    async with _job_context(job):
        try:
            await self._dispatch(job)
            if handle:
                await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
            logger.info("worker.job_done", job_id=job.job_id, command=job.command)
        except Exception as exc:
            logger.error("worker.job_failed", ...)
```

The logic:

1. **Extract `_receipt_handle` and the `job` body.** SQS messages have metadata; we keep the receipt handle for `delete_message`.
2. **Parse the job.** It's a JSON-serialized `Job` pydantic model. If it doesn't parse, we delete the message (it's broken; retrying won't help) and move on.
3. **Bind log context.** `_job_context` is a tiny `asynccontextmanager` that sets `job_id`, `command`, and `user_phone` in the structlog context for the duration of the job. Every log line in the command gets these fields automatically.
4. **Dispatch.** If it succeeds, delete the message. If it raises, log and let the message re-appear after the visibility timeout.

Notice: **we don't delete on failure.** A failed job reappears in the queue after 15 minutes, ready for another attempt. SQS itself doesn't have a "max retries" — that's configured separately via the `RedrivePolicy`, which sends messages to the DLQ after `maxReceiveCount` failures. With a default of 5, a permanently broken job ends up in the DLQ where humans can inspect it.

## 8.6 — Dispatch

```python
async def _dispatch(self, job: Job) -> None:
    cls = cmd_registry.get(job.command)
    if cls is None:
        logger.warning("worker.command_not_registered", command=job.command)
        return
    deps = self._deps or build_deps()
    ctx = await _dispatcher.prepare_context(
        cast("Any", _FakeRouted(job.command, cls)),
        user=job.user,
        whatsapp=deps.whatsapp,
        http=deps.http,
        gemini=deps.gemini,
        s3=deps.s3,
        secrets=deps.secrets_manager,
        media_id=job.media_id,
        media_mime=job.media_mime,
        media_filename=job.media_filename,
    )
    cmd: Any = cls()
    await cmd.run(ctx)
```

The worker uses the same `dispatcher.prepare_context` as the Lambda. The `_FakeRouted` is a stand-in for `RoutedCommand` because the worker already has the class — it doesn't need to re-route the text.

Crucially: **the worker doesn't care whether the command was declared `sync=True` or `sync=False`.** It just runs them all. A `sync=True` command could be processed by the worker too (e.g. if the Lambda is having a bad day); the worker is the universal fallback. In practice the dispatcher in the Lambda routes based on the flag, but the worker is happy either way.

## 8.7 — Graceful shutdown

`worker/shutdown.py` is a 50-line module that handles SIGTERM and SIGINT. The minimum the systemd unit sends on `systemctl stop wactl-worker.service` is SIGTERM. SIGINT is for Ctrl-C in a local run.

```python
def install() -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig)

def _signal_handler(sig: int) -> None:
    _logger.info("worker.signal_received", signal=sig)
    _event().set()

def is_set() -> bool:
    ...
```

The event is created lazily inside a running event loop (asyncio's `Event` requires a loop). The handlers flip the event flag; the main loop checks it on every iteration:

```python
while not shutdown.is_set():
    await self._poll_once()
```

What "graceful" means here:

- **In-flight job finishes.** The current `_process_message` call runs to completion (including the SQS delete) before the loop exits.
- **No new polls.** The flag is checked at the top of every iteration, so a SIGTERM during a 20-second long-poll will be observed as soon as the poll returns.
- **30-second ceiling.** The systemd unit's `TimeoutStopSec=30` means: if the in-flight job takes longer than 30 seconds, systemd will SIGKILL. We picked 30s because most commands finish in <60s; jobs that take longer are usually stuck and a SIGKILL is fine.
- **No data loss.** If we crash mid-job without deleting the SQS message, the message re-appears after 15 minutes (the visibility timeout). The next worker (or the same one after restart) picks it up.

## 8.8 — The systemd unit

`worker/systemd/wactl-worker.service` is a standard systemd unit file:

```ini
[Unit]
Description=WACTL worker — long-polls SQS + dispatches async commands
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=wactl
Group=wactl
WorkingDirectory=/opt/wactl
EnvironmentFile=-/etc/wactl/worker.env
ExecStart=/opt/wactl/.venv/bin/python -m worker.main
Restart=on-failure
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=30
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/wactl /tmp
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Key points:

- **`Type=simple`** — systemd considers the service "started" as soon as the process launches. No forking.
- **`User=wactl`, `Group=wactl`** — runs as a non-root user. The user is created by cloud-init.
- **`EnvironmentFile=-/etc/wactl/worker.env`** — the `-` prefix means "ignore if missing." The env file is hand-written (or set by Terraform's user data) and contains the SSM parameter names + AWS region.
- **`Restart=on-failure`, `RestartSec=10`** — if the process dies unexpectedly, systemd restarts it after 10 seconds. Combined with SQS's at-least-once delivery, this gives effectively-once processing in practice.
- **`KillSignal=SIGTERM`** — explicit so systemd doesn't default to SIGKILL.
- **Hardening directives** — `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadWritePaths`, `PrivateTmp` are layered defense: the process can't escalate privileges, can't write outside `/var/log/wactl` and `/tmp`, can't see other users' homes, and has its own `/tmp`. A compromised worker process is much harder to weaponize.

This unit file is *not* in the worker tarball. It's baked into the cloud-init user data (`infra/ec2.tf`) and written to `/etc/systemd/system/wactl-worker.service` on first boot. The unit in the repo is the source of truth that Terraform copies from.

## 8.9 — The build: `worker/Dockerfile`

The worker is delivered as a single tarball (`worker.tar.gz`) uploaded to the releases S3 bucket. The build is a multi-stage Docker process:

```dockerfile
FROM python:3.12-slim AS builder

# System deps for compiling wheels for Pillow, pymupdf, lxml, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev libffi-dev \
        libjpeg-dev zlib1g-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the source + dep spec
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY worker ./worker

# Install uv, then use it to build a self-contained package set
RUN pip install --no-cache-dir uv && \
    uv export --frozen --no-hashes --format requirements-txt > /tmp/requirements.txt && \
    uv pip install --python /usr/local/bin/python --target /out/packages \
        --no-cache --no-compile-bytecode -r /tmp/requirements.txt

# Copy our package + worker entry point on top of the deps
RUN cp -r /src/src/wactl /out/packages/wactl && \
    cp -r /src/worker /out/worker

# Bundle as a single tarball
WORKDIR /out
RUN tar --owner=0 --group=0 -czf /out/worker.tar.gz packages worker && \
    sha256sum worker.tar.gz > worker.tar.gz.sha256

FROM scratch AS artifact
COPY --from=builder /out/worker.tar.gz /worker.tar.gz
COPY --from=builder /out/worker.tar.gz.sha256 /worker.tar.gz.sha256
```

Three things to notice:

1. **The first stage builds a self-contained `packages/` directory.** Every Python dep is installed there with `uv pip install --target`. No virtual env, no system-wide install — just a directory tree.
2. **The tarball is what's deployed.** It contains `packages/` (deps + our code) and `worker/` (the entry point). On the EC2 instance, it extracts to `/opt/wactl/`, giving us `/opt/wactl/packages/`, `/opt/wactl/worker/`, and `/opt/wactl/packages/wactl/` (the importable package).
3. **The second stage is a `scratch` image holding only the tarball.** When CI runs `docker build`, it can `docker create` and `docker cp` the artifact out without any of the build infrastructure.

The matching `.sha256` sidecar is used by the deploy step to verify the tarball wasn't corrupted in transit.

## 8.10 — The build script

`worker/build.sh` is the human/CI entry point:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker build -t wactl-worker-builder -f worker/Dockerfile .
mkdir -p dist
docker create --name wactl-worker-extract wactl-worker-builder /bin/true >/dev/null
docker cp wactl-worker-extract:/worker.tar.gz dist/worker.tar.gz
docker cp wactl-worker-extract:/worker.tar.gz.sha256 dist/worker.tar.gz.sha256
docker rm wactl-worker-extract >/dev/null

echo "[build_worker] Built dist/worker.tar.gz ($(du -h dist/worker.tar.gz | cut -f1))"
sha256sum -c dist/worker.tar.gz.sha256
```

The trick: build into a throwaway container, then `docker cp` the tarball out. This means CI doesn't need a working Python environment — it just needs Docker.

## 8.11 — First-boot setup (cloud-init)

The EC2 instance runs Amazon Linux 2023 (arm64). The Terraform launch template injects a cloud-init user data script (see `infra/ec2.tf`) that does the first-boot setup:

```text
#cloud-config
packages:
  - python3.12
  - tar
  - gzip
  - git
  - amazon-ssm-agent

users:
  - name: wactl
    system: true
    shell: /bin/bash
    home: /opt/wactl

runcmd:
  - mkdir -p /opt/wactl /var/log/wactl
  - chown -R wactl:wactl /opt/wactl /var/log/wactl
  - if [ ! -f /opt/wactl/.venv/bin/python ]; then
      aws s3 cp s3://wactl-dev-releases-<id>/worker.tar.gz /tmp/worker.tar.gz
      tar -xzf /tmp/worker.tar.gz -C /opt/wactl
      /opt/wactl/.venv/bin/python -m ensurepip --upgrade || true
    fi
  - cat > /etc/systemd/system/wactl-worker.service <<UNIT
    [the systemd unit]
    UNIT
  - systemctl daemon-reload
  - systemctl enable --now wactl-worker.service
```

The crucial detail: `if [ ! -f /opt/wactl/.venv/bin/python ]` — the install is **idempotent**. If the instance is replaced (e.g. ASG scales up a new one, or an instance refresh), the existing extracted files are detected and the download is skipped. This is also why the user data is safe to re-run on instance refresh.

## 8.12 — What the worker does NOT do

To keep the file readable, the worker is intentionally thin:

- ❌ It doesn't validate the job (the dispatcher and command do).
- ❌ It doesn't know which command is sync vs async (it just runs them).
- ❌ It doesn't retry failed jobs (SQS visibility timeout + DLQ does that).
- ❌ It doesn't monitor itself (CloudWatch does — chapter 17).

If you find yourself adding business logic to `worker/main.py`, you're putting it in the wrong place. The worker is plumbing; the commands are the product.

## 8.13 — What "good" looks like

A healthy worker:

- Polls SQS once every 20 seconds (when the queue is empty)
- Wakes up immediately when a message arrives
- Processes one job at a time, sequentially
- Logs every job with a `job_id` and the user phone
- Deletes the SQS message only on success
- Stays below 200 MB RAM (t4g.nano has 512 MB)

If you're seeing the worker use more than 200 MB, the Gemimi or pdf2docx import is probably the culprit — they're heavy libraries. If you see the worker OOM-killed, the ASG replaces the instance, but the failed job is re-delivered via the SQS visibility timeout.

## Next

→ [`09-data-and-storage.md`](09-data-and-storage.md) — S3, DynamoDB, SSM Parameter Store: what each is, what we store there, and why.
