# ─── Lambda execution role ────────────────────────────────────────────
# Least-privilege permissions for the webhook Lambda:
# • CloudWatch Logs write
# • S3 RW to media bucket (downloading inbound + uploading outbound media)
# • DynamoDB RW to dedup table (try_claim / conditional put)
# • SQS send (for /pdf-audio async dispatch — FIFO queue)
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
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${local.suffix}-webhook",
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${local.suffix}-webhook:*",
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
# The worker is the only consumer of the FIFO jobs queue, the media
# bucket (read+write), and the releases bucket (read worker.tar.gz on
# first boot via cloud-init). Session Manager access is handled by the
# AWS-managed AmazonSSMManagedInstanceCore policy attached below.
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
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/wactl/${local.suffix}/worker",
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/wactl/${local.suffix}/worker:*",
    ]
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
    sid       = "ReleasesBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.releases.bucket}/*"]
  }
}

resource "aws_iam_role_policy" "worker_policy" {
  name   = "${local.suffix}-worker-inline"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker_policy.json
}

# Session Manager (SSM) so you can shell into the worker without SSH.
resource "aws_iam_role_policy_attachment" "worker_ssm" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "worker" {
  name = "${local.suffix}-worker"
  role = aws_iam_role.worker.name
}
