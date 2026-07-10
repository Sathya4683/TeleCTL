# ─── Lambda execution role ────────────────────────────────────────────
# Least-privilege permissions for the webhook Lambda:
# • CloudWatch Logs write
# • Secrets read (app secret for HMAC verify)
# • S3 RW to media bucket (downloading inbound + uploading outbound media)
# • DynamoDB RW to dedup table (try_claim / conditional put)
# • SQS send (for async dispatch)
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
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid    = "SecretsRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
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

resource "aws_iam_role_policy" "lambda_policy" {
  name   = "${local.suffix}-lambda-inline"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}

# ─── EC2 worker IAM ───────────────────────────────────────────────────
# Same trust set as before but bounded to ec2.amazonaws.com + we attach
# the AWS SSM Session Manager policy for ops access (optional).
data "aws_iam_policy_document" "worker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${local.suffix}-worker"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
}

data "aws_iam_policy_document" "worker_policy" {
  statement {
    sid    = "Logs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid       = "SqsConsume"
    effect    = "Allow"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.jobs.arn]
  }

  statement {
    sid       = "MediaBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.media.bucket}/*"]
  }

  statement {
    sid    = "SecretsRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      local.whatsapp_access_token_secret_arn,
      local.whatsapp_app_secret_arn,
    ]
  }
}

resource "aws_iam_role_policy" "worker_policy" {
  name   = "${local.suffix}-worker-inline"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker_policy.json
}

resource "aws_iam_instance_profile" "worker" {
  name = "${local.suffix}-worker"
  role = aws_iam_role.worker.name
}

# ─── GitHub Actions OIDC role ────────────────────────────────────────
# Trust policy restricts the role to a single repo + branch via the OIDC
# `sub` claim. Update `github_org` / `github_repo` below (or use a
# variable) before first apply.
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

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780a973"]
}

resource "aws_iam_role" "github_actions" {
  name               = "${local.suffix}-gha-deploy"
  assume_role_policy = data.aws_iam_policy_document.gha_assume.json
}

data "aws_iam_policy_document" "gha_policy" {
  statement {
    sid       = "StateBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      "arn:aws:s3:::wactl-tf-state-${local.account_id}",
      "arn:aws:s3:::wactl-tf-state-${local.account_id}/*",
    ]
  }

  statement {
    sid    = "ReleaseBucket"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.releases.arn,
      "${aws_s3_bucket.releases.arn}/*",
    ]
  }

  statement {
    sid    = "LambdaOps"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:PublishVersion",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = ["arn:aws:lambda:${data.aws_region.current.name}:${local.account_id}:function:${local.suffix}-webhook"]
  }

  statement {
    sid       = "EC2ASG"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances", "autoscaling:*"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "gha_policy" {
  name   = "${local.suffix}-gha-inline"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.gha_policy.json
}
