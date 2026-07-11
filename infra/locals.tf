locals {
  # Name suffix: applies to every resource to disambiguate envs.
  suffix = "${var.project_name}-${var.env}"

  # Account ID is needed for bucket names (must be globally unique).
  account_id = data.aws_caller_identity.current.account_id

  # Common tags merged on top of the provider-level defaults.
  tags = {
    Project     = var.project_name
    Environment = var.env
    ManagedBy   = "terraform"
    Repository  = "github.com/sathya-narayanan/wactl"
  }

  # ARNs of the SSM SecureString parameters managed in secrets.tf.
  # Used both as IAM resource scopes and as env-var values passed to the
  # webhook Lambda. SSM accepts the full ARN for get_parameter.
  whatsapp_access_token_secret_arn = aws_ssm_parameter.whatsapp_access_token.arn
  whatsapp_app_secret_arn          = aws_ssm_parameter.whatsapp_app_secret.arn
  whatsapp_verify_token_arn        = aws_ssm_parameter.whatsapp_verify_token.arn
}
