# WACTL Infrastructure (Terraform)

Provisions the AWS footprint for the Telegram bot: HTTP API Gateway v2,
Lambda, SQS FIFO, DynamoDB, S3, EC2 worker ASG, and the supporting IAM.

## Layout

| File | Purpose |
|------|---------|
| `provider.tf` | AWS provider pinning, region, default tags. |
| `backend.tf` | **Local** backend (`terraform.tfstate` on disk). No S3 state bucket. |
| `variables.tf` | `env`, `project_name`, `region`, plus the Telegram / Gemini secrets passed at apply time. |
| `locals.tf` | Common name suffix, account-id, tags. |
| `data.tf` | Caller identity + region lookups. |
| `outputs.tf` | `api_gateway_url`, `sqs_jobs_queue_url`, `media_bucket`. |
| `apigateway.tf` | HTTP API v2 + `POST /telegram/webhook` route → Lambda. No explicit `$default` stage (AWS auto-manages it). |
| `lambda.tf` | Webhook Lambda (Python 3.12, 512 MB, 300 s timeout). |
| `iam.tf` | Lambda exec role + EC2 worker instance role + SSM managed-policy attachment. |
| `sqs.tf` | FIFO jobs queue + FIFO DLQ (with redrive). |
| `dynamodb.tf` | Dedup table (pay-per-request, TTL on `expires_at`). |
| `s3.tf` | Media bucket (1-day lifecycle, SSE-S3, public block) + Releases bucket (worker tarball). |
| `ec2.tf` | AL2023 arm64 launch template + ASG (1 × t4g.nano) + cloud-init that writes `/etc/wactl/worker.env`. |
| `cloudwatch.tf` | Two log groups (Lambda + worker). No alarms (the original three were unwired SNS topics). |

## Quick start

State is local. No S3 bootstrap.

```bash
cd infra
terraform fmt -recursive
terraform init
terraform validate

# Apply with secrets passed as vars (do NOT commit these)
export TELEGRAM_BOT_TOKEN=123456:ABCDEF...
export TELEGRAM_WEBHOOK_SECRET_TOKEN=$(openssl rand -hex 32)
export GEMINI_API_KEY=AIza...

terraform apply \
  -var "telegram_bot_token=${TELEGRAM_BOT_TOKEN}" \
  -var "telegram_webhook_secret_token=${TELEGRAM_WEBHOOK_SECRET_TOKEN}" \
  -var "gemini_api_key=${GEMINI_API_KEY}"

# Note the URL to register with Telegram
terraform output -raw api_gateway_url
```

## Why HTTP API v2 (not REST)

Cheaper (~$1/M vs ~$5/M requests), simpler config, and we don't need any
REST-only features (no API keys, no usage plans, no request validation).
The Lambda proxy works identically via `aws_apigatewayv2_integration` +
`aws_apigatewayv2_route`.

## Why SQS FIFO (not Standard)

Only one async command (`/pdf-audio`) and per-user ordering matters
(replay an old job over a new one for the same chat_id → confusing).
The webhook enqueues with `MessageGroupId = chat_id`. Throughput cap
(300 msg/s) is well above personal use.

## Why EC2 (not Fargate / Lambda-only)

`/pdf-audio` does TTS fan-out across chunks (30-120 s) and needs
system `ffmpeg` for WAV→MP3 mux. Lambda has no `ffmpeg` layer handy,
so we run a single always-on t4g.nano (AWS free tier, 750 hrs/mo
for 12 months from account creation).

## Trade-offs to be aware of

1. **Secrets in EC2 user-data.** `TELEGRAM_BOT_TOKEN` and
   `GEMINI_API_KEY` are baked into the cloud-init `write_files` block
   because SSM Parameter Store adds Lambda-style latency + IAM cost.
   Anyone with `ec2:DescribeInstances` can read the user-data, so
   don't share the account with strangers. Switch to SSM if that
   changes (the worker IAM role already has `ssm:GetParameter` —
   just uncomment the SSM block in `iam.tf`).
2. **Free tier requires default VPC.** `data "aws_subnets" "default"`
   fails in accounts that explicitly deleted the default VPC. Either
   create a VPC + subnets + update the data source, or re-enable the
   default VPC in the console.
3. **No alarms.** `cloudwatch.tf` only provisions log groups. If you
   want DLQ-depth or error alarms, add `aws_cloudwatch_metric_alarm`
   resources + an SNS topic to publish to.
