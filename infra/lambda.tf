# Webhook Lambda — the thin entry point invoked by API Gateway.
# Packaging is a zip built by CI (`uv pip install --target packages …`)
# and uploaded as the deployment package.
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

  depends_on = [
    aws_iam_role_policy.lambda_policy,
    aws_cloudwatch_log_group.lambda_webhook,
  ]

  tags = local.tags
}
