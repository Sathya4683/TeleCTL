# 11 — Infrastructure as Code (Terraform)

All of WACTL's AWS infrastructure is defined in `infra/` as Terraform files. This chapter walks through every file, every resource, and the reasoning behind the choices. If you've never used Terraform before, read this carefully — it's the longest chapter for a reason.

## 11.1 — What Terraform is (and why we use it)

Terraform is HashiCorp's **Infrastructure as Code** tool. You write `.tf` files describing the resources you want (S3 buckets, Lambda functions, IAM roles). Terraform reads them, computes the difference between your declared state and the live state, and applies the changes via AWS APIs.

The key property: **declarative, not imperative.** You don't say "create the S3 bucket, then add a lifecycle rule, then add public-access-block." You say "the S3 bucket should exist with these properties," and Terraform figures out the API calls to make.

```hcl
resource "aws_s3_bucket" "media" {
  bucket = "${local.suffix}-media-${local.account_id}"
  tags   = local.tags
}
```

That one block creates a bucket. The `tags = local.tags` and `${local.suffix}` references are resolved at apply time.

The trade-off: Terraform has a learning curve. The AWS provider has 1000+ resource types, each with their own quirks. But for our use case, the resource count is small (about 20 resources total), so the surface is manageable.

## 11.2 — The file layout

```
infra/
├── README.md                  # the infra-specific quickstart
├── provider.tf                # AWS provider + default tags
├── backend.tf                 # S3 backend (state + lockfile)
├── variables.tf               # env, project_name, region, domain
├── locals.tf                  # name suffix, account_id, common ARNs
├── outputs.tf                 # URLs and ARNs to surface
├── data.tf                    # data sources (caller identity, current region)
├── apigateway.tf              # REST API + /webhook resource + GET/POST methods
├── lambda.tf                  # the webhook Lambda + env vars
├── iam.tf                     # all 3 roles + the OIDC provider + the GHA policy
├── sqs.tf                     # the jobs queue + DLQ
├── dynamodb.tf                # the dedup table
├── s3.tf                      # the media + releases buckets
├── secrets.tf                 # the 3 SSM SecureString parameters
├── ec2.tf                     # the launch template + ASG + security group + user data
├── cloudwatch.tf              # the 2 log groups + 3 alarms
└── eventbridge.tf             # the (disabled) daily cleanup rule
```

One file per concern. Some files have multiple related resources (`apigateway.tf` has the API, the methods, the deployment, the stage, and the Lambda permission) but each resource is a small block.

## 11.3 — `provider.tf`: the AWS provider

```hcl
terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}
```

The `required_version` pins the Terraform CLI version. The `required_providers` block pins the AWS provider version (`~> 5.50` means "5.50 or any 5.x, but not 6.x").

The `default_tags` block is a feature of the AWS provider: any tag you list here is automatically applied to every resource the provider manages. This is how every resource in WACTL gets `Project`, `Environment`, and `ManagedBy` tags without listing them on each one.

## 11.4 — `backend.tf`: where state lives

```hcl
terraform {
  backend "s3" {
    key            = "wactl/terraform.tfstate"
    use_lockfile   = true
    encrypt        = true
  }
}
```

**State** is Terraform's record of "what I created last time." Without it, Terraform can't know what's already deployed vs. what needs to be created. We store the state in S3.

The bucket name and region are *not* in this file — they're passed at `terraform init` time via `-backend-config`. This is intentional: the state bucket itself is created out-of-band (before the first `init`), so Terraform doesn't try to manage its own state location.

`use_lockfile = true` enables Terraform 1.10's native S3 lockfile (a separate `.tflock` file in the same bucket). Without locking, two simultaneous `terraform apply` runs would race and corrupt the state.

`encrypt = true` server-side encrypts the state file with S3-managed keys. The state contains sensitive data (resource IDs, sometimes secret values referenced in plain text), so encryption is a baseline.

## 11.5 — `variables.tf`: the inputs

```hcl
variable "env" {
  description = "Deployment environment: dev, staging, prod. Used as a name suffix."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be one of dev, staging, prod."
  }
}

variable "project_name" { ... }
variable "region" { ... }
variable "domain" { ... }
```

Four variables. The `env` validation block catches typos at `terraform plan` time: if you pass `ENV=production` (a common mistake), `terraform plan` fails with the message "env must be one of dev, staging, prod."

These are passed via `-var` flags or env vars (`TF_VAR_env=dev`) or a `terraform.tfvars` file (which is gitignored).

## 11.6 — `locals.tf`: shared values

```hcl
locals {
  suffix = "${var.project_name}-${var.env}"
  account_id = data.aws_caller_identity.current.account_id
  tags = {
    Project     = var.project_name
    Environment = var.env
    ManagedBy   = "terraform"
    Repository  = "github.com/sathya-narayanan/wactl"
  }
  whatsapp_access_token_secret_arn = aws_ssm_parameter.whatsapp_access_token.arn
  whatsapp_app_secret_arn          = aws_ssm_parameter.whatsapp_app_secret.arn
  whatsapp_verify_token_arn        = aws_ssm_parameter.whatsapp_verify_token.arn
}
```

`locals` are computed values used in many places. `local.suffix` ("wactl-dev") is appended to every resource name. `local.account_id` is needed for globally-unique bucket names. `local.tags` is the merged set of common tags (the provider's `default_tags` plus `Repository`).

The three `whatsapp_*_arn` locals pre-compute the ARNs of the SSM parameters so they can be referenced both in IAM policies and in Lambda env vars without circular dependencies.

## 11.7 — `data.tf`: querying AWS

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
```

**Data sources** are read-only queries to AWS. `aws_caller_identity` returns the AWS account ID of whoever is running Terraform. `aws_region` returns the region from the provider config. Both are used in `locals.tf` and `outputs.tf`.

## 11.8 — `sqs.tf`: the queue and DLQ

```hcl
resource "aws_sqs_queue" "jobs_dlq" {
  name                       = "${local.suffix}-jobs-dlq"
  message_retention_seconds  = 1209600  # 14 days
  visibility_timeout_seconds = 900      # 15 min
  sqs_managed_sse_enabled    = true
  tags                       = local.tags
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${local.suffix}-jobs"
  message_retention_seconds  = 345600   # 4 days
  visibility_timeout_seconds = 900      # 15 min
  receive_wait_time_seconds  = 20       # long poll
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 5
  })

  tags = local.tags
}
```

Two queues:

- **`jobs`** is the main queue. The Lambda enqueues here; the worker polls here.
  - `message_retention_seconds = 345600` = 4 days. A message lives at most 4 days before SQS deletes it.
  - `visibility_timeout_seconds = 900` = 15 minutes. While a worker is processing, the message is invisible. If the worker takes longer than 15 minutes (or crashes), the message reappears.
  - `receive_wait_time_seconds = 20` = long poll. The worker's `receive_message` blocks for up to 20 seconds, so an empty queue doesn't generate empty API calls.
  - `redrive_policy` tells SQS: "after 5 receive attempts, move the message to the DLQ." This is how SQS implements "max retries."
- **`jobs_dlq`** is the dead-letter queue. A message lands here after 5 failed processing attempts.
  - 14-day retention — enough time for a human to inspect and decide.

The `sqs_managed_sse_enabled = true` enables SQS-managed server-side encryption (SSE-SQS). Free, and encrypts message bodies at rest.

The `redrive_policy` is a JSON-encoded string. SQS requires this format; the `jsonencode` function is Terraform's way to build a JSON string from a HCL map.

## 11.9 — `dynamodb.tf`: the dedup table

```hcl
resource "aws_dynamodb_table" "dedup" {
  name         = "${local.suffix}-dedup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.tags
}
```

One table, one attribute (the primary key), TTL enabled, point-in-time recovery enabled. See chapter 09 for the design rationale.

The `PAY_PER_REQUEST` billing mode means we pay per request, not per provisioned capacity. At our scale this is essentially free; for high-traffic systems you'd want to switch to `PROVISIONED` with auto-scaling.

## 11.10 — `s3.tf`: the two buckets

```hcl
resource "aws_s3_bucket" "media" {
  bucket        = "${local.suffix}-media-${local.account_id}"
  force_destroy = false
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    id     = "expire-old-media"
    status = "Enabled"
    expiration {
      days = 1
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
```

For each bucket we declare four resources:

1. **`aws_s3_bucket`** — the bucket itself.
2. **`aws_s3_bucket_public_access_block`** — disables all four public-access vectors. This is belt-and-suspenders: even if someone accidentally attaches a public policy, the block prevents it.
3. **`aws_s3_bucket_lifecycle_configuration`** — auto-delete objects after N days.
4. **`aws_s3_bucket_server_side_encryption_configuration`** — AES256 server-side encryption.

The `releases` bucket is configured similarly, but with a different lifecycle (keep noncurrent versions for 30 days, abort incomplete multipart uploads after 7 days).

`force_destroy = false` means Terraform won't delete the bucket if it has objects in it. To delete a bucket with objects, you must empty it manually first. This is a safety belt against `terraform destroy` going wrong.

## 11.11 — `secrets.tf`: the SSM parameters

```hcl
resource "aws_ssm_parameter" "whatsapp_access_token" {
  name        = "wactl/whatsapp/access-token"
  description = "WhatsApp Cloud API system-user access token."
  type        = "SecureString"
  value       = "CHANGEME-populate-via-aws-ssm-put-parameter"
  tags        = local.tags
}
```

Three placeholders. The real values are populated out-of-band (see chapter 09):

```bash
aws ssm put-parameter --name "/wactl/whatsapp/access-token" \
    --type SecureString --value "EAAxxxx..." --overwrite
```

Terraform won't overwrite on subsequent applies (it would refuse to change a SecureString without explicit `overwrite = true`, which we don't set).

## 11.12 — `iam.tf`: the three roles

This is the most important file in the repo. IAM is the security backbone; getting it right is non-negotiable.

### Lambda execution role

```hcl
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.suffix}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid    = "Logs"
    effect = "Allow"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    sid    = "SecretsRead"
    effect = "Allow"
    actions = ["ssm:GetParameter"]
    resources = [
      local.whatsapp_app_secret_arn,
      local.whatsapp_access_token_secret_arn,
      local.whatsapp_verify_token_arn,
    ]
  }
  statement {
    sid       = "MediaBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.media.bucket}/*"]
  }
  statement {
    sid       = "DedupTable"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.dedup.arn]
  }
  statement {
    sid       = "EnqueueAsync"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.jobs.arn]
  }
}
```

The pattern: one `data "aws_iam_policy_document"` block for the assume-role policy (which says "this role can be assumed by lambda.amazonaws.com"), one for the permissions policy (which says "when assumed, allow these specific actions on these specific resources").

The permissions are **least-privilege**:

- `ssm:GetParameter` only on the three WhatsApp parameters (not all of `/wactl/*`).
- S3 RW only on the media bucket (not all S3).
- DynamoDB only on the dedup table (not all tables).
- SQS send only on the jobs queue (not all queues).

The Lambda cannot list buckets, cannot scan the dedup table, cannot receive messages from the queue. Each action is scoped to a specific resource ARN.

### EC2 worker role

```hcl
data "aws_iam_policy_document" "worker_policy" {
  statement {
    sid    = "SqsConsume"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.jobs.arn]
  }
  statement {
    sid       = "MediaBucket"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.media.bucket}/*"]
  }
  statement {
    sid    = "SecretsRead"
    actions = ["ssm:GetParameter"]
    resources = [
      local.whatsapp_access_token_secret_arn,
      local.whatsapp_app_secret_arn,
    ]
  }
}
```

The worker role has SQS *receive* (Lambda has only *send*). It does not have DynamoDB access (it doesn't dedup — only the Lambda does). It does not have SSM access to the verify token (the worker never gets a GET handshake).

`aws_iam_instance_profile` wraps the role in a profile that EC2 can attach to the instance.

### GitHub Actions OIDC role

```hcl
data "aws_iam_policy_document" "gha_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:sathya-narayanan/wactl:ref:refs/heads/main"]
    }
  }
}
```

This is the OIDC trust policy. The `sub` condition restricts the role to assume only from the `sathya-narayanan/wactl` repo on the `main` branch. A PR from a fork would have a different `sub` and be rejected.

The role's permissions:

- S3 RW on the state bucket and the releases bucket.
- Lambda `UpdateFunctionCode` and `UpdateFunctionConfiguration` on the webhook function.
- `ec2:DescribeInstances` and `autoscaling:*` (for instance refreshes after worker deploys).

This is the only way to do CI/CD without long-lived AWS access keys. See chapter 16 for the full OIDC story.

## 11.13 — `apigateway.tf`: the API

```hcl
resource "aws_api_gateway_rest_api" "webhook" {
  name        = "${local.suffix}-webhook"
  description = "WACTL webhook receiver."

  binary_media_types = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "audio/ogg", "audio/mpeg",
    "image/jpeg", "image/png", "image/webp",
  ]

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}
```

A REST API (not HTTP API) — chosen for native binary media support and per-method IAM authorization. The cost differential is negligible.

`binary_media_types` lists the MIME types API Gateway should pass through as bytes (not base64-encoded). For our use case, the inbound POST is always JSON (so the list is more about outbound docs/images/audio that WhatsApp might send as webhook payloads, though the webhook itself is JSON).

`endpoint_configuration.types = ["REGIONAL"]` is cheaper than `EDGE` (no CloudFront distribution) and lower latency than `PRIVATE`.

```hcl
resource "aws_api_gateway_resource" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  parent_id   = aws_api_gateway_rest_api.webhook.root_resource_id
  path_part   = "webhook"
}

resource "aws_api_gateway_method" "get_webhook" {
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  resource_id   = aws_api_gateway_resource.webhook.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_webhook" {
  rest_api_id             = aws_api_gateway_rest_api.webhook.id
  resource_id             = aws_api_gateway_resource.webhook.id
  http_method             = aws_api_gateway_method.get_webhook.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.webhook.invoke_arn
}
```

The pattern: a **resource** (`/webhook`), two **methods** (GET for handshake, POST for messages), each with an **integration** that points to the Lambda. The `AWS_PROXY` integration type means API Gateway passes the entire HTTP request (headers, body, query string, etc.) to the Lambda as a single JSON event.

```hcl
resource "aws_api_gateway_deployment" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id

  triggers = {
    redeploy_hash = sha1(jsonencode([
      aws_api_gateway_resource.webhook.id,
      aws_api_gateway_method.get_webhook.id,
      aws_api_gateway_method.post_webhook.id,
      aws_api_gateway_integration.get_webhook.id,
      aws_api_gateway_integration.post_webhook.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}
```

A **deployment** is the API Gateway concept of "a snapshot of the routes." Every time the routes change, we want a new deployment to be applied. The `triggers` block does that automatically: any change to the listed resources changes the hash, which changes the deployment, which forces API Gateway to pick up the new routes.

`create_before_destroy = true` is required because we want zero-downtime updates — the new deployment is created before the old one is destroyed.

```hcl
resource "aws_api_gateway_stage" "webhook" {
  rest_api_id      = aws_api_gateway_rest_api.webhook.id
  deployment_id    = aws_api_gateway_deployment.webhook.id
  stage_name       = var.env
  description      = "${var.env} environment."
  cache_cluster_enabled = false
}
```

A **stage** is the URL path under which the API is exposed: `https://<api-id>.execute-api.<region>.amazonaws.com/<env>/webhook`. With `env=dev`, the webhook URL ends in `/dev/webhook`. We use the env as the stage name so dev/staging/prod have different URLs.

```hcl
resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.webhook.execution_arn}/*/*"
}
```

This is the Lambda's "trust policy" — it says "API Gateway is allowed to invoke me." Without this, the Lambda would refuse invocations from API Gateway even if the integration is configured.

## 11.14 — `lambda.tf`: the webhook function

```hcl
resource "aws_lambda_function" "webhook" {
  function_name    = "${local.suffix}-webhook"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda.webhook.handler.lambda_handler"
  runtime          = "python3.12"
  filename         = "${path.module}/../build/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../build/lambda.zip")
  timeout          = 60
  memory_size      = 512
  architectures    = ["x86_64"]

  environment {
    variables = {
      WACTL_ENV                    = var.env
      AWS_REGION                   = data.aws_region.current.name
      LOG_LEVEL                    = "INFO"
      WHATSAPP_APP_SECRET_SECRET   = local.whatsapp_app_secret_arn
      WHATSAPP_ACCESS_TOKEN_SECRET = local.whatsapp_access_token_secret_arn
      WHATSAPP_VERIFY_TOKEN_SECRET = local.whatsapp_verify_token_arn
      MEDIA_BUCKET                 = aws_s3_bucket.media.bucket
      DEDUP_TABLE                  = aws_dynamodb_table.dedup.name
      JOBS_QUEUE                   = aws_sqs_queue.jobs.url
    }
  }
}
```

The `handler` is `lambda.webhook.handler.lambda_handler` — the file is `lambda/webhook/handler.py`, the function is `lambda_handler`. The `runtime = "python3.12"` matches our `.python-version` file.

`timeout = 60` and `memory_size = 512` are the runtime settings. 60 seconds is plenty for any sync command; 512 MB is more than enough (a Pillow resize of a 10 MB image uses ~200 MB). Lambda is billed per ms and per MB-ms; we could tune this down for cost.

`source_code_hash` is the SHA256 of the deployment zip. When the zip changes, Terraform forces a redeploy.

The `environment.variables` are passed to the Lambda at runtime. `MEDIA_BUCKET`, `DEDUP_TABLE`, and `JOBS_QUEUE` tell the code where to find each resource. The three `WHATSAPP_*_SECRET` values are SSM parameter names (or ARNs); the code calls `secrets.get_secret(name)` which fetches the actual value with caching.

`architectures = ["x86_64"]` is the explicit default. We don't currently use arm64 for the Lambda (only the EC2 worker does).

## 11.15 — `ec2.tf`: the worker fleet

```hcl
data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["137112412989"] # Amazon
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }
}

resource "aws_security_group" "worker" {
  name        = "${local.suffix}-worker-sg"
  description = "Egress-only security group for the worker fleet."

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

The AMI is the latest Amazon Linux 2023 (arm64) — free, small (~150 MB), and pre-installed with `python3.12` (the system Python, not the Lambda's). The owner ID `137112412989` is Amazon's official AWS account; using that filter means we only get official AMIs.

The security group is **egress-only** — no inbound rules. The worker doesn't accept connections from anywhere; it only makes outbound calls (to SQS, S3, the WhatsApp API, etc.).

```hcl
data "cloudinit_config" "worker" {
  ...
  part {
    content = <<-EOT
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
        - |
          if [ ! -f /opt/wactl/.venv/bin/python ]; then
            aws s3 cp s3://${aws_s3_bucket.releases.bucket}/worker.tar.gz /tmp/worker.tar.gz
            tar -xzf /tmp/worker.tar.gz -C /opt/wactl
            /opt/wactl/.venv/bin/python -m ensurepip --upgrade || true
          fi
        - cat > /etc/systemd/system/wactl-worker.service <<UNIT
          [the systemd unit]
          UNIT
        - systemctl daemon-reload
        - systemctl enable --now wactl-worker.service
    EOT
  }
}
```

Cloud-init runs on first boot. The script:

1. Installs `python3.12` and a few small tools.
2. Creates a `wactl` system user.
3. Downloads `worker.tar.gz` from the releases bucket (idempotent — only if `/opt/wactl/.venv/bin/python` doesn't exist).
4. Writes the systemd unit and starts the service.

The idempotency check is important: instance refreshes (where ASG replaces the instance) will run cloud-init again, and we don't want to re-download the tarball on every refresh.

```hcl
resource "aws_launch_template" "worker" {
  name_prefix   = "${local.suffix}-worker-"
  image_id      = data.aws_ami.al2023_arm64.id
  instance_type = "t4g.nano"
  user_data     = data.cloudinit_config.worker.rendered

  vpc_security_group_ids = [aws_security_group.worker.id]
  iam_instance_profile {
    name = aws_iam_instance_profile.worker.name
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"  # IMDSv2 enforced
    http_put_response_hop_limit = 1
  }
}
```

The launch template bundles the AMI, instance type, security group, IAM profile, and the cloud-init user data. `http_tokens = "required"` enforces IMDSv2 (the v2 metadata service, which requires a PUT request with a token). This is a security control: SSRF attacks that try to read the instance's IAM credentials from the metadata service are mitigated by requiring the v2 token.

```hcl
resource "aws_autoscaling_group" "worker" {
  name                = "${local.suffix}-worker"
  vpc_zone_identifier = data.aws_subnets.default.ids
  desired_capacity    = 1
  min_size            = 1
  max_size            = 2
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }
}
```

The ASG keeps 1 worker running, scales to 2 if needed. `vpc_zone_identifier = data.aws_subnets.default.ids` uses the default VPC's subnets; for a real production deploy, you'd point this at private subnets in a custom VPC.

## 11.16 — `cloudwatch.tf`: logs and alarms

```hcl
resource "aws_cloudwatch_log_group" "lambda_webhook" {
  name              = "/aws/lambda/${local.suffix}-webhook"
  retention_in_days = 30
  tags              = local.tags
}

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
```

Log groups: one for the Lambda (`/aws/lambda/...` is the convention), one for the worker. 30-day retention keeps storage costs down.

Three alarms:

- **`dlq_depth`** — fires if any messages land in the DLQ. A signal that something is broken.
- **`lambda_errors`** — fires if the Lambda throws (other than the "swallow everything" return-200 path).
- **`worker_cpu`** — fires if the worker CPU exceeds 80% for 15 minutes (3 × 5-minute periods).

None of the alarms have `alarm_actions` set — the infra creates the alarms but doesn't define where to send notifications. That's deliberate: the destination (email, Slack, PagerDuty) is environment-specific and out of scope for v1. To enable notifications, add `alarm_actions = [aws_sns_topic.alerts.arn]` to each alarm and create the SNS topic.

## 11.17 — `eventbridge.tf`: the (disabled) cleanup

```hcl
resource "aws_cloudwatch_event_rule" "cleanup" {
  name                = "${local.suffix}-cleanup"
  description         = "Daily DynamoDB dedup-table scan."
  schedule_expression = "cron(0 3 * * ? *)"  # 03:00 UTC
  is_enabled          = false
}
```

A daily cleanup rule that would invoke a (not-yet-built) Lambda to scan the dedup table and remove orphaned rows. The rule is defined but disabled (`is_enabled = false`) because the cleanup Lambda is a stub. When the cleanup feature is built, enable the rule and uncomment the target blocks below.

We declare the rule now so the schedule is reviewable alongside the rest of the infra; the implementation lands later.

## 11.18 — `outputs.tf`: what to surface

```hcl
output "api_gateway_url" {
  description = "Webhook URL — configure this in Meta Developer dashboard."
  value       = "${aws_api_gateway_stage.webhook.invoke_url}/webhook"
}

output "sqs_jobs_queue_url" { ... }
output "dynamodb_dedup_table" { ... }
...
```

Outputs are values Terraform prints at the end of `apply`. The webhook URL is the one a human needs to paste into the Meta developer console; the others are mostly for reference or for use in CI scripts.

## 11.19 — How to actually run it

```bash
# First time (or after major changes):
cd infra
terraform init \
    -backend-config="bucket=wactl-tf-state-<account-id>" \
    -backend-config="region=us-east-1"
terraform plan -out=plan.tfplan
terraform apply plan.tfplan

# Subsequent changes:
terraform plan
terraform apply
```

The state bucket (`wactl-tf-state-<account-id>`) is created out-of-band, typically by a one-time `aws s3api create-bucket` invocation. The state file is encrypted at rest by S3 and access-controlled by the GHA role.

`terraform plan` shows the diff; you read it before applying. `terraform apply` does it. The plan file (`plan.tfplan`) is binary and tied to your state; you can't reuse it from another machine.

## 11.20 — Why not AWS CDK or CloudFormation?

Three reasons we chose Terraform over the alternatives:

- **State is portable.** The `.tfstate` file is JSON; you can read it, grep it, move it. CloudFormation state is internal to AWS and unreadable.
- **HCL is explicit.** No magic; you can see every resource. CDK generates CloudFormation from Python, which is a layer of indirection we don't need.
- **The community is larger.** For any AWS question, "Terraform" is one of the top search hits. CDK is catching up but not there yet.

The cost: Terraform has its own learning curve, and the AWS provider occasionally has bugs that take a release to fix. For a small project, this is fine.

## Next

→ [`12-security-and-iam.md`](12-security-and-iam.md) — deeper on the security posture: HMAC, IAM least-privilege, OIDC, and what's NOT in scope.
