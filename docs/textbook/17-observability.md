# 17 — Observability: Logs, Metrics, Alarms

You can't fix what you can't see. WACTL has three observability surfaces:

1. **Logs** — structured JSON lines on stdout, captured by CloudWatch Logs.
2. **Metrics** — emitted by AWS services (Lambda, SQS, EC2), surfaced in CloudWatch.
3. **Alarms** — CloudWatch metric alarms that page you when something is wrong.

This chapter walks through each, the philosophy, and the practical details of using them.

## 17.1 — Why structured logging

The traditional log line looks like this:

```text
2026-01-15 10:23:45,123 INFO  wactl.webhook: Command /pdf-docx succeeded for user 15551234567
```

The problem: parsing this line is fragile. The format can change between log calls; the fields are positional; you can't easily filter by user_phone without regex.

The structured alternative:

```json
{"event": "command.sync.complete", "level": "info", "timestamp": "2026-01-15T10:23:45.123Z", "command": "/pdf-docx", "user_phone": "15551234567", "success": true}
```

The same information, but every field is a key. CloudWatch Logs Insights can query by field:

```text
fields @timestamp, command, user_phone
| filter event = "command.sync.complete"
| stats count() by command
```

This is what `structlog` gives us. Every log line is one JSON object per line, suitable for CloudWatch's parser.

## 17.2 — The structlog config

`src/wactl/logging.py` sets up the structured logger:

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
```

The processor chain (in order):

1. **`merge_contextvars`** — adds any contextvars bound via `bind_context()`. This is how `message_id` and `user_phone` get attached to every log line within a request.
2. **`add_log_level`** — adds `"level": "info"` (or `debug`, `warning`, etc.).
3. **`TimeStamper(fmt="iso", utc=True)`** — adds `"timestamp": "2026-01-15T10:23:45.123Z"`.
4. **`StackInfoRenderer`** — adds a stack trace if `stack_info=True` was passed.
5. **`format_exc_info`** — converts `exc_info=True` into `"exception": "...", "exception_type": "..."`.
6. **`JSONRenderer`** — final step: convert the dict to a JSON string.

`PrintLoggerFactory(file=sys.stdout)` writes to stdout. CloudWatch captures stdout.

The stdlib `logging` (used by boto3, urllib3, etc.) is also configured to write to stdout with `format="%(message)s"`. The result: every log line — structlog or stdlib — is one JSON object per line.

We also quiet the noisy libraries:

```python
for noisy in ("botocore", "boto3", "s3transfer", "urllib3", "httpx", "asyncio"):
    logging.getLogger(noisy).setLevel(max(level, logging.WARNING))
```

Without this, a single boto3 call can produce 5-10 log lines of internal details. We want to see our own log lines, not the SDK's.

## 17.3 — Bound context

`bind_context` is the most useful structlog feature. It attaches key-value pairs to every log line in the current scope:

```python
with bind_context(message_id="wamid.ABC", user_phone="15551234567"):
    logger.info("command.sync.complete", command="/pdf-docx", success=True)
    # ... do work ...
    logger.info("command.sync.done", bytes=12345)
```

Both log lines get `message_id` and `user_phone` automatically. No need to pass them in every call.

It's implemented with `contextvars` (Python's mechanism for per-async-task state). This means the context propagates correctly across `await` boundaries and `asyncio.to_thread` calls.

The webhook uses this to bind per-request context:

```python
for parsed in payloads:
    with bind_context(message_id=parsed.user.message_id, user_phone=parsed.user.phone):
        ...
```

The worker binds per-job context:

```python
@asynccontextmanager
async def _job_context(job):
    bind_context(job_id=job.job_id, command=job.command, user_phone=job.user.phone)
    try:
        yield
    finally:
        reset_context()
```

`reset_context` at the end ensures the next job starts clean.

The Lambda's `handle` function also calls `reset_context` at the start:

```python
def handle(event, context=None, *, deps=None):
    reset_context()  # clear any leftover from previous invocations
    ...
```

This is critical: Lambda containers are reused across invocations. Without `reset_context`, context from the previous invocation would leak into the next one.

## 17.4 — Log levels

`structlog` (and stdlib) have five levels:

| Level | When to use |
|---|---|
| `DEBUG` | Verbose, only useful when debugging. Disabled by default. |
| `INFO` | Normal operation. "Job done." "Command started." |
| `WARNING` | Something unexpected but recoverable. "User input error." |
| `ERROR` | Something failed. "Job failed after 5 attempts." |
| `CRITICAL` | Reserved. We don't currently use it. |

The level is set via the `LOG_LEVEL` env var. Default is `INFO`. In production we keep `INFO` (the cost of `DEBUG` is too high — every boto3 call would log a dozen lines).

## 17.5 — CloudWatch log groups

Two log groups are configured in `infra/cloudwatch.tf`:

```hcl
resource "aws_cloudwatch_log_group" "lambda_webhook" {
  name              = "/aws/lambda/${local.suffix}-webhook"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/wactl/${local.suffix}/worker"
  retention_in_days = 30
}
```

- **`/aws/lambda/<name>`** — the Lambda convention. AWS creates this automatically; we just configure retention.
- **`/wactl/<name>/worker`** — custom path. The worker writes here via the AWS CLI or CloudWatch agent (currently via a custom log writer; see chapter 08).

30-day retention is the default. We could go longer (CloudWatch charges per GB-month), but for a personal-scale system, 30 days is plenty to debug most issues.

## 17.6 — CloudWatch Logs Insights: querying the logs

The web console at <https://console.aws.amazon.com/cloudwatch/home#logs-insights> lets you query the log groups. Some useful queries:

**All log lines for a specific message:**

```text
fields @timestamp, @message
| filter message_id = "wamid.ABC"
| sort @timestamp asc
```

**All errors in the last hour:**

```text
fields @timestamp, @message
| filter level = "error"
| sort @timestamp desc
| limit 100
```

**Command throughput by command:**

```text
fields @timestamp, command
| filter event = "command.sync.complete"
| stats count() by command
```

**Failed jobs in the DLQ:**

```text
fields @timestamp, @message
| filter event = "worker.job_failed"
| sort @timestamp desc
| limit 50
```

The query language is SQL-like. You can do `filter`, `stats`, `sort`, `limit`. See the [CloudWatch Logs Insights docs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html) for the full syntax.

## 17.7 — Metrics

Metrics are numerical time series. AWS services emit them automatically:

| Service | Metric | What it means |
|---|---|---|
| **Lambda** | `Invocations` | How many times the function was called. |
| **Lambda** | `Errors` | How many invocations threw. |
| **Lambda** | `Duration` | How long each invocation took. |
| **Lambda** | `Throttles` | How many invocations were rejected due to concurrency limits. |
| **SQS** | `ApproximateNumberOfMessagesVisible` | How many messages are in the queue. |
| **SQS** | `ApproximateNumberOfMessagesNotVisible` | How many messages are in flight (visibility timeout). |
| **EC2** | `CPUUtilization` | Average CPU across the instance's cores. |
| **EC2** | `NetworkIn` / `NetworkOut` | Bytes per second. |

You can see all of these in the CloudWatch console under Metrics → All metrics. We don't emit any custom application metrics (yet); the AWS-provided metrics are enough.

## 17.8 — Alarms

`infra/cloudwatch.tf` configures three alarms:

```hcl
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${local.suffix}-dlq-depth"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1

  dimensions = {
    QueueName = aws_sqs_queue.jobs_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.suffix}-webhook-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 1

  dimensions = {
    FunctionName = aws_lambda_function.webhook.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_cpu" {
  alarm_name          = "${local.suffix}-worker-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.worker.name
  }
}
```

### `dlq_depth`

Fires if any messages are in the DLQ. A single message in the DLQ is a sign that a job failed 5 times in a row. The threshold is 1 (anything ≥ 1 triggers).

`period = 300` (5 minutes) and `evaluation_periods = 1` means: check once every 5 minutes, fire if the threshold is met in any single check.

### `lambda_errors`

Fires if the Lambda's `Errors` metric ≥ 1 in any 1-minute period. We *swallow* most errors (return 200), so this metric only fires on truly unhandled exceptions — the kind that indicate a code bug.

`period = 60` (1 minute), `evaluation_periods = 1`.

### `worker_cpu`

Fires if the worker's CPU exceeds 80% for 15 minutes (3 × 5-minute periods). A sustained high CPU means the worker is overloaded — either there's a job backlog or a runaway process.

### What we don't have

- **No SNS topic for notifications.** The alarms exist but have no `alarm_actions` set. To enable notifications, create an SNS topic and add `alarm_actions = [aws_sns_topic.alerts.arn]` to each alarm.
- **No PagerDuty / Slack integration.** Without an SNS topic, the alarms only show in the CloudWatch console. For personal scale, you check the console periodically; for production, you'd wire up SNS → email/Slack.
- **No custom application metrics.** Lambda duration, SQS depth, and EC2 CPU are AWS-provided. We don't emit things like "command count by user" or "API error rate" — useful but not currently implemented.

## 17.9 — The DLQ inspection flow

When a job fails 5 times, it lands in the DLQ. To inspect:

1. **CloudWatch console** → SQS → Queues → `<env>-jobs-dlq` → "Send and receive messages" → "Poll for messages".

2. **AWS CLI:**

```bash
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/<account>/wactl-dev-jobs-dlq \
  --max-number-of-messages 10 \
  --visibility-timeout 0
```

The `--visibility-timeout 0` keeps the messages visible (they don't get marked as in-flight, so subsequent receives see them).

3. **For each message, the body is the JSON-serialized `Job`:**

```json
{
  "job_id": "...",
  "command": "/pdf-docx",
  "args": "",
  "user": {"phone": "15551234567", ...},
  "media_id": "...",
  "enqueued_at": "2026-01-15T10:00:00Z",
  "meta": {"name": "/pdf-docx", "sync": false, "requires_media": true, ...}
}
```

4. **Inspect the job's data, look at the worker's logs** for the corresponding `job_id` to see why it failed.

5. **Decide:** is this a permanent failure (bad data, code bug) or transient? If transient, re-enqueue the message to the main queue. If permanent, leave it in the DLQ for later analysis.

A "re-drive to source" feature in the SQS console can re-enqueue all DLQ messages at once.

## 17.10 — What we don't do

- **No distributed tracing.** No OpenTelemetry, no X-Ray. The Lambda + worker + WhatsApp hop would benefit from tracing, but adding it requires instrumenting every integration and a tracing backend. Out of scope for v1.
- **No real-time dashboards.** CloudWatch dashboards are possible (and AWS has a "Lambda + SQS" sample dashboard), but we don't have one.
- **No log-based metrics.** You can derive custom metrics from log queries (e.g. "count of /pdf-audio commands per hour"), but we don't currently do this.
- **No synthetic monitoring.** No canary that sends a fake webhook every 5 minutes to verify the system is up. CloudWatch Synthetics or a third-party (Pingdom, UptimeRobot) would do this.
- **No error tracking.** No Sentry, no Rollbar. CloudWatch Logs + the alarm on `lambda_errors` is the equivalent.

For a personal-scale system, this is enough. For a production system, you'd add these in order: SNS notifications → custom metrics → distributed tracing → synthetic monitoring.

## 17.11 — The on-call experience

If you're woken up at 3am by an alarm, the runbook is:

1. **Check the alarm:** CloudWatch console → Alarms → which one fired?
2. **Check the relevant logs:**
   - DLQ depth alarm → `wactl-dev-worker` log group. Search for `worker.job_failed` or `error`.
   - Lambda errors alarm → `/aws/lambda/wactl-dev-webhook` log group. Search for `error` or `exception`.
   - Worker CPU alarm → `wactl-dev-worker` log group. Look for a runaway process or a job that's been running too long.
3. **Look at the recent deploys:** GitHub → Actions → see if anything was deployed in the last hour.
4. **Decide:**
   - Bad deploy? Revert the commit.
   - Bad data in the DLQ? Inspect, decide if transient, re-drive or leave.
   - Runaway process? Terminate the EC2 instance; ASG launches a new one.
5. **Document.** Note what happened in a post-mortem.

This is intentionally manual. For a personal system, automation isn't worth the complexity.

## Next

→ [`18-glossary.md`](18-glossary.md) — every term used in the textbook, defined.
