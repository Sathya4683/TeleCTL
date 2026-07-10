output "api_gateway_url" {
  description = "Webhook URL — configure this in Meta Developer dashboard."
  value       = "${aws_api_gateway_stage.webhook.invoke_url}/webhook"
}

output "webhook_lambda_name" {
  description = "Name of the webhook Lambda."
  value       = aws_lambda_function.webhook.function_name
}

output "webhook_lambda_arn" {
  description = "ARN of the webhook Lambda."
  value       = aws_lambda_function.webhook.arn
}

output "sqs_jobs_queue_url" {
  description = "URL of the async jobs queue."
  value       = aws_sqs_queue.jobs.url
}

output "sqs_jobs_queue_arn" {
  description = "ARN of the async jobs queue."
  value       = aws_sqs_queue.jobs.arn
}

output "sqs_dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.jobs_dlq.url
}

output "dynamodb_dedup_table" {
  description = "Name of the dedup table."
  value       = aws_dynamodb_table.dedup.name
}

output "media_bucket" {
  description = "Name of the media S3 bucket."
  value       = aws_s3_bucket.media.bucket
}

output "ec2_worker_role_arn" {
  description = "IAM role assumed by the worker EC2 instances."
  value       = aws_iam_role.worker.arn
}

output "github_actions_role_arn" {
  description = "IAM role assumed by GitHub Actions via OIDC."
  value       = aws_iam_role.github_actions.arn
}

output "secrets_prefix" {
  description = "ARN prefix of the WhatsApp secrets."
  value       = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:wactl/${var.env}/whatsapp"
}
