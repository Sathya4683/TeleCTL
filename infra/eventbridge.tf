# Daily cleanup Lambda is intentionally a stub for v1. The plan reserves
# the rule + target, but the Lambda function itself lives under
# `lambda/scheduler/` and will be wired in Phase 11. Keeping the rule
# here means the schedule is reviewable alongside the rest of the infra.
resource "aws_cloudwatch_event_rule" "cleanup" {
  name                = "${local.suffix}-cleanup"
  description         = "Daily DynamoDB dedup-table scan."
  schedule_expression = "cron(0 3 * * ? *)" # 03:00 UTC
  is_enabled          = false
}

# ─── Stub targets (disabled until cleanup Lambda is provisioned) ──
# resource "aws_cloudwatch_event_target" "cleanup" {
#   rule = aws_cloudwatch_event_rule.cleanup.name
#   arn  = aws_lambda_function.scheduler.arn
# }
#
# resource "aws_lambda_permission" "allow_eventbridge" {
#   statement_id  = "AllowEventBridge"
#   action        = "lambda:InvokeFunction"
#   function_name = aws_lambda_function.scheduler.function_name
#   principal     = "events.amazonaws.com"
#   source_arn    = aws_cloudwatch_event_rule.cleanup.arn
# }
