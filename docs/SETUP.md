# WACTL — Setup guide (Telegram bot)

This guide walks you through bringing WACTL from zero to a live
Telegram bot. Expect about 45 minutes if your AWS account and
Telegram bot are already in place.

---

## 0. Prerequisites

| Tool      | Version | Notes                                |
|-----------|---------|--------------------------------------|
| Python    | 3.12    | matches `.python-version`            |
| uv        | latest  | `pip install uv`                     |
| Terraform | 1.10+   | `brew install tfenv && tfenv install`|
| AWS CLI   | v2      | configured with a sandbox admin user |
| Docker    | 24+     | only for building the worker tarball |

You'll also need:

- An **AWS account** with a sandbox admin IAM user (for the first `terraform apply`).
- A **Telegram account** + a bot created via [@BotFather](https://t.me/BotFather).
- A **Google Gemini API key** (free tier) if you want `/pdf-audio`.

---

## 1. Clone & install

```bash
git clone https://github.com/sathya-narayanan/wactl
cd wactl

# Python deps + virtualenv (managed by uv)
uv sync
```

Run the test suite — it should pass with zero AWS credentials:

```bash
uv run pytest tests -q
```

---

## 2. Create your Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`. Pick a display name and a username ending in `bot`.
3. Copy the **bot token** — it looks like `123456:ABCDEF...`. You'll pass it to Terraform later.
4. (Optional, recommended.) Send `/setdomain` if you own a domain; otherwise skip.
5. (Optional.) Send `/setprivacy` → **Disable** so the bot can read commands in groups. Skip if you only use private chats.

---

## 3. Get a Gemini API key (only needed for `/pdf-audio`)

1. Visit <https://aistudio.google.com/app/apikey> and create an API key.
2. Free tier covers personal-scale usage (~15 requests/min, 1500/day).

Skip this if you don't care about `/pdf-audio` — the rest of the bot works fine without it.

---

## 4. Apply Terraform

State is local (`infra/terraform.tfstate`) — no S3 bootstrap needed.

```bash
cd infra

# (One-time, optional.) Format and validate the configuration.
terraform fmt -recursive
terraform validate

# Apply with your secrets as vars. Do NOT commit these to git.
export TELEGRAM_BOT_TOKEN=123456:ABCDEF...
export TELEGRAM_WEBHOOK_SECRET_TOKEN=$(openssl rand -hex 32)
export GEMINI_API_KEY=AIza...

terraform init
terraform apply \
  -var "telegram_bot_token=${TELEGRAM_BOT_TOKEN}" \
  -var "telegram_webhook_secret_token=${TELEGRAM_WEBHOOK_SECRET_TOKEN}" \
  -var "gemini_api_key=${GEMINI_API_KEY}"
```

Resources created:

- 1× HTTP API Gateway v2 + stage + 1 route (`POST /telegram/webhook`).
- 1× Lambda function (Python 3.12, x86_64, 512 MB, 300 s timeout).
- 1× SQS FIFO queue + 1× FIFO DLQ.
- 1× DynamoDB table (pay-per-request, TTL on `expires_at`).
- 1× S3 media bucket + 1× releases bucket.
- 1× EC2 launch template + ASG (1 × t4g.nano).
- 2× CloudWatch log groups (Lambda + worker).
- 2× IAM roles (Lambda exec, EC2 worker).

Note the output `api_gateway_url` — that's what you'll register with Telegram in step 6.

---

## 5. Build & upload the Lambda + worker

The Lambda needs a deployable zip; the worker runs from a tarball that the EC2 cloud-init downloads. Build both:

```bash
cd ..

# Lambda zip
rm -rf build/lambda packages
mkdir -p build/lambda
uv export --frozen --no-hashes --format requirements-txt > /tmp/requirements.txt
uv pip install \
  --python "$(which python)" \
  --target build/lambda/packages \
  --no-cache --no-compile-bytecode \
  -r /tmp/requirements.txt
cp -r src/wactl build/lambda/packages/wactl
cp -r lambda/webhook build/lambda/lambda
(cd build/lambda/packages && zip -qr ../../lambda.zip .)
(cd build/lambda/lambda && zip -qr ../../lambda.zip .)

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp build/lambda.zip \
  "s3://wactl-dev-releases-${ACCOUNT_ID}/lambda.zip"

# Worker tarball (requires Docker)
bash worker/build.sh
aws s3 cp dist/worker.tar.gz \
  "s3://wactl-dev-releases-${ACCOUNT_ID}/worker.tar.gz"
```

The worker ASG will refresh on the next instance launch (or you can force it):

```bash
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name wactl-dev-worker
```

For the Lambda code change, update the function code directly:

```bash
aws lambda update-function-code \
  --function-name wactl-dev-webhook \
  --s3-bucket "wactl-dev-releases-${ACCOUNT_ID}" \
  --s3-key lambda.zip
```

---

## 6. Register the webhook with Telegram

Get the API Gateway URL from Terraform:

```bash
cd infra && terraform output -raw api_gateway_url
```

Then register it with Telegram (one-time, manual):

```bash
WEBHOOK_URL=$(terraform output -raw api_gateway_url)
SECRET="your-webhook-secret-token-here"

curl -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${WEBHOOK_URL}\", \"secret_token\": \"${SECRET}\"}"
```

If you didn't set `TELEGRAM_WEBHOOK_SECRET_TOKEN` in Terraform, omit the `secret_token` field.

Verify:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

You should see your URL listed with `pending_update_count = 0`.

---

## 7. Send your first message

Open Telegram, DM your bot, send `/help`. You should receive a list
of 5 commands within a second:

- `/help` — show this message
- `/image-resize WxH` — resize an attached photo
- `/image-compress q=70 max=1600` — recompress an attached photo
- `/pdf-docx` — convert an attached PDF into a Word document
- `/pdf-audio` — convert an attached PDF into an MP3 audiobook

Try `/image-resize 800x600` with any photo attached.

---

## 8. IAM role setup (already created by Terraform)

Terraform creates these IAM roles automatically:

- `wactl-dev-lambda-exec` — assumed by the webhook Lambda. Permissions:
  S3 RW on the media bucket, DynamoDB RW on the dedup table, SQS send
  on the jobs FIFO queue, CloudWatch Logs.
- `wactl-dev-worker` — instance role assumed by the EC2 worker. Permissions:
  SQS consume on the jobs FIFO queue, S3 RW on the media bucket, S3 read
  on the releases bucket (for cloud-init tarball download), CloudWatch Logs,
  Session Manager (`AmazonSSMManagedInstanceCore`).

To inspect:

```bash
aws iam get-role --role-name wactl-dev-lambda-exec
aws iam get-role --role-name wactl-dev-worker
```

To shell into the worker:

```bash
aws ssm start-session --target "$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=wactl-dev-worker" \
  --query "Reservations[0].Instances[0].InstanceId" --output text)"
```

---

## 9. Run the worker locally (optional)

For dev iteration, run the worker against the real AWS queue:

```bash
uv run python -m worker.main
```

Environment variables `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `SQS_JOBS_QUEUE_URL`,
`AWS_REGION` need to be set in your shell or `.env`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Telegram says "webhook not set" | `setWebhook` call failed or bot token wrong | Re-run `curl .../setWebhook` with the correct token. |
| Telegram returns "Unauthorized" on every message | Bot token mismatch between Lambda env and what you registered with | Re-deploy with the right `TELEGRAM_BOT_TOKEN`. |
| Lambda returns 401 | `X-Telegram-Bot-Api-Secret-Token` mismatch | Make sure the `secret_token` you set on `setWebhook` matches the Lambda env var. |
| `/pdf-audio` returns nothing | EC2 worker not running | Check ASG in EC2 console; check `/wactl/wactl-dev/worker` log group. |
| SQS messages piling up | Worker stuck or crashed | Check worker logs; check the DLQ. |
| `terraform apply` errors | Local state out of sync | `terraform plan` first; check for stale resources to import or destroy. |

---

## What's next?

- The other 5 commands (`merge-pdf`, `split-pdf`, `translate`, `web-summary`, `github-pr`) are still in the codebase — just not imported. To re-enable, add the import back to `src/wactl/commands/__init__.py` and (for sync commands) flip `sync=True` in the `@register` decorator.
- See `docs/telegram-cheatsheet.md` for the full Bot API reference.
