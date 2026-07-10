# REST API (not HTTP API) — chosen for native binary media support and
# per-method IAM authorisation. The cost differential is negligible.
resource "aws_api_gateway_rest_api" "webhook" {
  name        = "${local.suffix}-webhook"
  description = "WACTL webhook receiver."

  binary_media_types = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "audio/ogg",
    "audio/mpeg",
    "image/jpeg",
    "image/png",
    "image/webp",
  ]

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = local.tags
}

resource "aws_api_gateway_resource" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  parent_id   = aws_api_gateway_rest_api.webhook.root_resource_id
  path_part   = "webhook"
}

# GET /webhook — hub verification handshake.
resource "aws_api_gateway_method" "get_webhook" {
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  resource_id   = aws_api_gateway_resource.webhook.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_webhook" {
  rest_api_id             = aws_api_gateway_rest_api.webhook.id
  resource_id             = aws_api_gateway_resource.webhook.id
  http_method             = aws_api_gateway_method.get_webhook.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.webhook.invoke_arn
}

# POST /webhook — the real handler.
resource "aws_api_gateway_method" "post_webhook" {
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  resource_id   = aws_api_gateway_resource.webhook.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "post_webhook" {
  rest_api_id             = aws_api_gateway_rest_api.webhook.id
  resource_id             = aws_api_gateway_resource.webhook.id
  http_method             = aws_api_gateway_method.post_webhook.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.webhook.invoke_arn
}

resource "aws_api_gateway_deployment" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id

  triggers = {
    redeploy_hash = sha1(jsonencode([
      aws_api_gateway_resource.webhook.id,
      aws_api_gateway_method.get_webhook.id,
      aws_api_gateway_method.post_webhook.id,
      aws_api_gateway_integration.get_webhook.id,
      aws_api_gateway_integration.post_webhook.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.get_webhook,
    aws_api_gateway_integration.post_webhook,
  ]
}

resource "aws_api_gateway_stage" "webhook" {
  rest_api_id      = aws_api_gateway_rest_api.webhook.id
  deployment_id    = aws_api_gateway_deployment.webhook.id
  stage_name       = var.env
  description      = "${var.env} environment."
  cache_cluster_enabled = false

  tags = local.tags
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.webhook.execution_arn}/*/*"
}
