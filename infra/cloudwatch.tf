# Log groups — 30 day retention by default; bumped per-group for noisy
# ones (e.g. webhook Lambda).
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

# ─── Alarms ─────────────────────────────────────────────────────────
# Each alarm posts to a topic you create later (email/Slack via SNS).

# DLQ depth > 0 — something is failing repeatedly.
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${local.suffix}-dlq-depth"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Jobs DLQ has pending messages — check worker logs."

  dimensions = {
    QueueName = aws_sqs_queue.jobs_dlq.name
  }
}

# Webhook Lambda errors.
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.suffix}-webhook-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Webhook Lambda is throwing — check CloudWatch logs."

  dimensions = {
    FunctionName = aws_lambda_function.webhook.function_name
  }
}

# Worker CPU high — could indicate a runaway job.
resource "aws_cloudwatch_metric_alarm" "worker_cpu" {
  alarm_name          = "${local.suffix}-worker-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Worker CPU > 80% for 15 min — check job backlog."
}
