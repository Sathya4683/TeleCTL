# Single-table dedup record. Keyed on Telegram message_id.
# TTL drops stale rows after 7 days — well beyond any plausible retry
# window for Telegram (which doesn't auto-retry at all, but we keep
# the TTL for safety against duplicate deliveries).
resource "aws_dynamodb_table" "dedup" {
  name         = "${local.suffix}-dedup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = local.tags
}
