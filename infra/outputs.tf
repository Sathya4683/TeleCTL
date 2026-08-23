output "api_gateway_url" {
  description = "Webhook URL — register this with the Telegram setWebhook API. The $default stage is auto-managed, so we read api_endpoint directly off the API."
  value       = "${aws_apigatewayv2_api.webhook.api_endpoint}/telegram/webhook"
}

output "sqs_jobs_queue_url" {
  description = "URL of the async jobs FIFO queue."
  value       = aws_sqs_queue.jobs.url
}

output "media_bucket" {
  description = "Name of the media S3 bucket."
  value       = aws_s3_bucket.media.bucket
}
