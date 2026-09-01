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
}
