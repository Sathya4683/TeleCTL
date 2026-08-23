# Log groups — 30 day retention. Both groups are created up-front so
# the Lambda / EC2 instance can write to them without needing
# `logs:CreateLogGroup` on the role.
resource "aws_cloudwatch_log_group" "lambda_webhook" {
  name              = "/aws/lambda/${local.suffix}-webhook"
  retention_in_days = 30

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/wactl/${local.suffix}/worker"
  retention_in_days = 30

  tags = local.tags
}
