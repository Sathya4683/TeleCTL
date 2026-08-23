# Webhook Lambda — the thin entry point invoked by API Gateway.
# Packaging is a zip built by `uv pip install --target packages …`
# and uploaded as the deployment package.
#
# Memory: 512 MB covers the worst case (pdf_docx with pdf2docx in-process).
# Timeout: 300 s covers a busy /pdf-docx on a 50-page PDF; /pdf-audio
#   runs on the EC2 worker, not here.
resource "aws_lambda_function" "webhook" {
  function_name    = "${local.suffix}-webhook"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda.webhook.handler.lambda_handler"
  runtime          = "python3.12"
  filename         = "${path.module}/../build/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../build/lambda.zip")
  timeout          = 300
  memory_size      = 512
  architectures    = ["x86_64"]

  environment {
    variables = {
      ENV                           = var.env
      AWS_REGION                    = var.region
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
  ]

  tags = local.tags
}
