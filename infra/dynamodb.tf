# Single-table dedup record. Keyed on the Meta WAMID (the unique message ID).
# TTL drops stale rows automatically after 7 days — matches Meta's retry
# window so we never re-process a message that's beyond the API's interest.
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

  point_in_time_recovery {
    enabled = true
  }

  tags = local.tags
}
