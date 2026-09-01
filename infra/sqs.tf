# FIFO queue — the only async command is /pdf-audio, and per-user
# ordering matters (don't replay an old job over a new one for the same
# chat). The webhook enqueues with `message_group_id = chat_id`.

# Dead-letter queue — jobs that fail repeatedly land here.
resource "aws_sqs_queue" "jobs_dlq" {
  name                        = "${local.suffix}-jobs-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1209600 # 14 days
  visibility_timeout_seconds  = 900     # 15 min
  sqs_managed_sse_enabled     = true

  tags = local.tags
}

# Main jobs queue. Long-poll (20 s) for cost efficiency.
resource "aws_sqs_queue" "jobs" {
  name                        = "${local.suffix}-jobs.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  message_retention_seconds   = 345600 # 4 days
  visibility_timeout_seconds  = 900    # 15 min — enough for the worst job
  receive_wait_time_seconds   = 20     # long poll
  sqs_managed_sse_enabled     = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.tags
}
