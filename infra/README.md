# WACTL Infrastructure (Terraform)

This directory provisions the entire AWS footprint of the WACTL platform:
API Gateway, Lambda, SQS, DynamoDB, S3, Secrets Manager, the EC2 worker
ASG, CloudWatch alarms, and the GitHub Actions OIDC role.

## Layout

| File | Purpose |
|------|---------|
| `provider.tf` | AWS provider pinning, region, default tags. |
| `backend.tf` | S3 backend with `use_lockfile = true`. |
| `variables.tf` | `env`, `project_name`, `region`, `domain`. |
| `locals.tf` | Common name suffix, ARN assembly, common tags. |
| `outputs.tf` | API URL, queue URL, table name, bucket, role ARNs. |
| `apigateway.tf` | REST API + `/webhook` (GET verify, POST Lambda proxy). |
| `lambda.tf` | Webhook Lambda function + IAM role + log group. |
| `iam.tf` | All IAM: Lambda exec, Worker instance, GHA OIDC. |
| `sqs.tf` | Jobs queue + DLQ with redrive. |
| `dynamodb.tf` | Dedup table with TTL. |
| `s3.tf` | Media bucket, lifecycle, public-block, KMS optional. |
| `secrets.tf` | Secrets Manager placeholders. |
| `ec2.tf` | Launch template, ASG, SG, IAM instance profile. |
| `cloudwatch.tf` | Log groups + alarms (DLQ depth, errors, latency, CPU). |
| `eventbridge.tf` | Daily cleanup rule (placeholder). |

## Quick start

```bash
# Bootstrap the state bucket (one-time)
aws s3api create-bucket \
  --bucket wactl-tf-state-${AWS_ACCOUNT_ID} \
  --region us-east-1 \
  --create-bucket-configuration LocationConstraint=us-east-1
aws s3api put-bucket-versioning \
  --bucket wactl-tf-state-${AWS_ACCOUNT_ID} \
  --versioning-configuration Status=Enabled

# Initialise + plan (no apply yet — secrets must be populated first)
cd infra
terraform init \
  -backend-config="bucket=wactl-tf-state-${AWS_ACCOUNT_ID}" \
  -backend-config="region=us-east-1"
terraform plan -var env=dev

# After secrets are populated (see docs/SETUP.md)
terraform apply -var env=dev -auto-approve
```

## Why REST API Gateway (vs HTTP API)

Native binary media support — lets us proxy uploads/downloads through a
single endpoint if we ever add a `/download` route. Cost differential is
~$1/M requests, acceptable for portfolio scale.

## Why SQS Standard (vs FIFO)

At-least-once is sufficient; jobs are idempotent (dedup via DynamoDB).
Throughput ceiling (unlimited) outweighs the ordering guarantee we don't
need. (See `docs/CODEBASE_GUIDE.md` for the full rationale.)

## Why EC2 (vs Fargate / Lambda)

Cheaper than Lambda for steady-state workload; matches the plan.
`docker-compose.yml` runs the worker locally for dev parity.
