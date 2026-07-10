# Pre-provision three Secrets Manager entries with placeholder values.
# Populate the real values via `aws secretsmanager put-secret-value`
# (see docs/SETUP.md) — Terraform will not overwrite on subsequent
# applies because `secret_string_wo` is not used.
resource "aws_secretsmanager_secret" "whatsapp_access_token" {
  name                    = "wactl/${var.env}/whatsapp/access-token"
  description             = "WhatsApp Cloud API system-user access token."
  recovery_window_in_days = 7

  tags = local.tags
}

resource "aws_secretsmanager_secret" "whatsapp_app_secret" {
  name                    = "wactl/${var.env}/whatsapp/app-secret"
  description             = "WhatsApp webhook HMAC app secret."
  recovery_window_in_days = 7

  tags = local.tags
}

resource "aws_secretsmanager_secret" "whatsapp_verify_token" {
  name                    = "wactl/${var.env}/whatsapp/verify-token"
  description             = "Webhook URL verification token (echoed in GET)."
  recovery_window_in_days = 7

  tags = local.tags
}
