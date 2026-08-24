# Webhook Lambda — container image deployed to AWS Lambda.
# We use a container image (10 GB max vs 50 MB zipped for direct upload)
# because ``pdf2docx`` transitively pulls in opencv-python-headless
# (~80 MB) + pymupdf (~60 MB), and we don't want to drop those deps.
#
# Memory: 512 MB covers the worst case (pdf_docx with pdf2docx in-process).
# Timeout: 300 s covers a busy /pdf-docx on a 50-page PDF; /pdf-audio
#   runs on the EC2 worker, not here.
#
# The image is built + pushed to ECR by docs/SETUP.md §5 step 2.
# The ECR repo URL is supplied as a Terraform variable (default empty
# so ``terraform validate`` doesn't fail before the image is built).
resource "aws_lambda_function" "webhook" {
  function_name = "${local.suffix}-webhook"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.webhook.repository_url}:${var.lambda_image_tag}"
  timeout       = 60
  memory_size   = 1024
  architectures = ["x86_64"]

  environment {
    variables = {
      # NOTE: AWS_REGION is a Lambda-reserved env var and is set
      # automatically from the function's deployment region.
      ENV                           = var.env
      LOG_LEVEL                     = "INFO"
      TELEGRAM_BOT_TOKEN            = var.telegram_bot_token
      TELEGRAM_WEBHOOK_SECRET_TOKEN = var.telegram_webhook_secret_token
      S3_MEDIA_BUCKET               = aws_s3_bucket.media.bucket
      DYNAMODB_DEDUP_TABLE          = aws_dynamodb_table.dedup.name
      SQS_JOBS_QUEUE_URL            = aws_sqs_queue.jobs.url
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_policy,
    aws_cloudwatch_log_group.lambda_webhook,
    aws_ecr_repository.webhook,
  ]

  tags = local.tags
}

# ECR repo holds the Lambda container image. Lifecycle policy keeps
# the last 5 images so old deploys can be rolled back to.
resource "aws_ecr_repository" "webhook" {
  name                 = "${local.suffix}-webhook"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "webhook" {
  repository = aws_ecr_repository.webhook.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}
