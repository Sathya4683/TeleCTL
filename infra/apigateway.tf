# HTTP API v2 (cheaper + simpler than REST API). One route:
#   POST /telegram/webhook → webhook Lambda
#
# Telegram does not use a GET handshake, so we don't need a GET method.
# The path matches the URL we'll register via the Telegram setWebhook API.

resource "aws_apigatewayv2_api" "webhook" {
  name          = "${local.suffix}-webhook"
  protocol_type = "HTTP"
  description   = "WACTL Telegram webhook receiver."

  tags = local.tags
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook_post" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /telegram/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

# NOTE: HTTP API v2 auto-creates and auto-manages a ``$default`` stage for
# every API. Explicitly creating it via ``aws_apigatewayv2_stage`` with
# ``name = "$default"`` fails at apply with ``ConflictException: Stage
# already exists``. We omit the stage resource and read the invoke URL
# from ``aws_apigatewayv2_api.webhook.api_endpoint`` in outputs.tf.
#
# Reference: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-stages.html
# ("If you created an API using quick create, the $default stage is managed
#  by API Gateway. You can't modify the $default stage.")

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*"
}
