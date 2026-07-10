# Dead-letter queue — jobs that fail repeatedly land here.
# Retention is 14 days, the Meta retry window for webhooks.
resource "aws_sqs_queue" "jobs_dlq" {
  name                       = "${local.suffix}-jobs-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 900      # 15 min — matches worker Lambda ceiling
  sqs_managed_sse_enabled    = true

  tags = local.tags
}

# Main jobs queue. Long-poll (20s) for cost efficiency; messages stay
# invisible for 15 min while the worker processes them.
resource "aws_sqs_queue" "jobs" {
  name                       = "${local.suffix}-jobs"
  message_retention_seconds  = 345600 # 4 days
  visibility_timeout_seconds = 900    # 15 min — enough for the worst job
  receive_wait_time_seconds  = 20     # long poll
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 5
  })

  tags = local.tags
}
