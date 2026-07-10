# WACTL — Setup guide

This guide walks you through bringing WACTL from zero to a live
WhatsApp bot. Expect about an hour if your AWS account and Meta
Developer account are already in place.

---

## 0. Prerequisites

| Tool      | Version | Notes                                |
|-----------|---------|--------------------------------------|
| Python    | 3.12    | matches `.python-version`            |
| uv        | latest  | `pip install uv`                     |
| Node      | 20+     | only for the frontend                |
| Terraform | 1.10+   | `brew install tfenv && tfenv install`|
| AWS CLI   | v2      | configured with a sandbox admin user |
| Docker    | 24+     | only for building the worker tarball |

You'll also need:

- An **AWS account** with a sandbox admin IAM user (for the first
  `terraform apply`).
- A **Meta Developer account** with a WhatsApp Business app + a System
  User access token.

---

## 1. Clone & install

```bash
git clone https://github.com/sathya-narayanan/wactl
cd wactl

# Python deps + virtualenv (managed by uv)
uv sync

# Frontend deps
cd web && npm install && cd ..
```

Run the test suite — it should pass with zero AWS credentials:

```bash
uv run pytest tests -q
```

---

## 2. Bootstrap the Terraform state bucket

Terraform state lives in S3. Create the bucket **once** by hand:

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3api create-bucket \
  --bucket wactl-tf-state-${AWS_ACCOUNT_ID} \
  --region us-east-1 \
  --create-bucket-configuration LocationConstraint=us-east-1
aws s3api put-bucket-versioning \
  --bucket wactl-tf-state-${AWS_ACCOUNT_ID} \
  --versioning-configuration Status=Enabled
```

---

## 3. Apply Terraform

```bash
cd infra
terraform init \
  -backend-config="bucket=wactl-tf-state-${AWS_ACCOUNT_ID}" \
  -backend-config="region=us-east-1"
terraform plan -var env=dev
terraform apply -var env=dev -auto-approve
```

Resources created:

- 1× REST API + 1 stage + 1 deployment + 2 methods (GET verify, POST).
- 1× Lambda function (Python 3.12, x86_64, 512 MB).
- 1× SQS queue + 1× DLQ.
- 1× DynamoDB table (pay-per-request, TTL on `expires_at`).
- 1× S3 media bucket + 1× releases bucket.
- 3× Secrets Manager secrets (placeholders).
- 1× EC2 launch template + ASG (1 instance).
- 4× CloudWatch log groups + 3 alarms.
- 1× IAM OpenID Connect Provider + 3× IAM roles.

Note the output `api_gateway_url` — that's what you'll register with
Meta in step 6.

---

## 4. Populate the secrets

The three secrets have placeholder values. Replace them with real ones:

```bash
export WA_PHONE_ID=...            # your WhatsApp phone-number ID
export WA_ACCESS_TOKEN=...        # system-user token (long-lived)
export WA_APP_SECRET=...          # from "App Settings" → "Webhook"
export WA_VERIFY_TOKEN=$(openssl rand -hex 32)

aws secretsmanager put-secret-value \
  --secret-id wactl/dev/whatsapp/access-token \
  --secret-string "$WA_ACCESS_TOKEN"

aws secretsmanager put-secret-value \
  --secret-id wactl/dev/whatsapp/app-secret \
  --secret-string "$WA_APP_SECRET"

aws secretsmanager put-secret-value \
  --secret-id wactl/dev/whatsapp/verify-token \
  --secret-string "$WA_VERIFY_TOKEN"
```

Keep `$WA_VERIFY_TOKEN` somewhere safe — Meta echoes it during the
webhook handshake and you'll paste it into the dashboard.

---

## 5. Build & upload the Lambda + worker

The Lambda needs a deployable zip; the worker runs from a tarball that
the EC2 cloud-init downloads. Build both:

```bash
# Lambda zip
cd ..
rm -rf build/lambda packages
mkdir -p build/lambda
uv export --frozen --no-hashes --format requirements-txt > /tmp/requirements.txt
uv pip install \
  --python "$(which python)" \
  --target build/lambda/packages \
  --no-cache --no-compile-bytecode \
  -r /tmp/requirements.txt
cp -r src/wactl build/lambda/packages/wactl
(cd build/lambda/packages && zip -qr ../../lambda.zip .)
(cd build/lambda && zip -qr ../lambda.zip lambda)

aws s3 cp build/lambda.zip \
  s3://wactl-dev-releases-${AWS_ACCOUNT_ID}/lambda.zip

# Worker tarball (requires Docker)
bash worker/build.sh
aws s3 cp dist/worker.tar.gz \
  s3://wactl-dev-releases-${AWS_ACCOUNT_ID}/worker.tar.gz
```

After upload, refresh the worker ASG so the new tarball is pulled:

```bash
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name wactl-dev-worker
```

---

## 6. Configure the WhatsApp webhook

In the Meta Developer dashboard:

1. **App → WhatsApp → Configuration → Webhook → Edit**
2. **Callback URL**: the `api_gateway_url` from `terraform output`
3. **Verify Token**: the `$WA_VERIFY_TOKEN` you generated above
4. **Webhook fields**: subscribe to `messages`
5. Click **Verify and save**

If verification fails: check CloudWatch Logs at
`/aws/lambda/wactl-dev-webhook` — the most common cause is an
app-secret mismatch.

---

## 7. Send your first message

Open WhatsApp, DM the business number, send `/help`. You should receive
a list of available commands within a second. Try `/image-resize
1024x768` with any photo attached.

---

## 8. Run the worker locally (optional)

For dev iteration, you can run the worker against the real AWS queue:

```bash
WACTL_ENV=dev \
AWS_REGION=us-east-1 \
WACTL_JOBS_QUEUE=https://sqs.us-east-1.amazonaws.com/${AWS_ACCOUNT_ID}/wactl-dev-jobs \
uv run python -m worker.main
```

Or, fully offline with mocked SQS:

```bash
uv run pytest tests/integration/test_worker.py -q
```

---

## 9. Frontend (Vercel)

The `web/` directory is a standalone Next.js 16 app. To deploy:

```bash
cd web
npx vercel deploy --prod
```

Set the environment variable `NEXT_PUBLIC_WA_ME_LINK` to your
business-number wa.me URL. (Default in `lib/site.ts` is a placeholder.)

---

## 10. CI/CD (GitHub Actions)

Add one repository secret:

| Name              | Value                              |
|-------------------|------------------------------------|
| `AWS_ACCOUNT_ID`  | your 12-digit AWS account id       |

That's it. Push to `main` and:

1. `ci.yaml` runs lint + mypy + tests.
2. `deploy.yaml` builds the Lambda + worker, uploads them to S3, then
   runs `terraform apply` using the OIDC role from step 3.

No long-lived AWS keys are ever stored in the repo.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Webhook verify fails | App secret mismatch | Re-populate `wactl/<env>/whatsapp/app-secret`. |
| Messages received but no reply | Worker not running | Check `/wactl/<env>/worker` log group. |
| Lambda timeout on async command | Command registered `sync=False` | Should be expected — Lambda replies instantly, worker does the work. |
| DLQ depth alarm fires | Repeated failures | Inspect the message body in SQS console. |
| `terraform apply` errors on OIDC provider | Already exists from prior run | `terraform import` it; or check `aws_iam_openid_connect_provider` in the console. |

---

## What's next?

- `docs/CODEBASE_GUIDE.md` — architecture tour for engineers.
- The GitHub repo's issues — feature requests and known limitations.