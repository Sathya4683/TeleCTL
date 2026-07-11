# Pre-provision three SSM Parameter Store (SecureString) entries with
# placeholder values. Populate the real values via
# `aws ssm put-parameter --type SecureString --value "..." --overwrite`
# (see docs/SETUP.md) — Terraform will not overwrite on subsequent
# applies. Stays on the Standard tier (free up to 10k parameters).
resource "aws_ssm_parameter" "whatsapp_access_token" {
  name        = "wactl/whatsapp/access-token"
  description = "WhatsApp Cloud API system-user access token."
  type        = "SecureString"
  value       = "CHANGEME-populate-via-aws-ssm-put-parameter"

  tags = local.tags
}

resource "aws_ssm_parameter" "whatsapp_app_secret" {
  name        = "wactl/whatsapp/app-secret"
  description = "WhatsApp webhook HMAC app secret."
  type        = "SecureString"
  value       = "CHANGEME-populate-via-aws-ssm-put-parameter"

  tags = local.tags
}

resource "aws_ssm_parameter" "whatsapp_verify_token" {
  name        = "wactl/whatsapp/verify-token"
  description = "Webhook URL verification token (echoed in GET)."
  type        = "SecureString"
  value       = "CHANGEME-populate-via-aws-ssm-put-parameter"

  tags = local.tags
}
