# S3 backend with native lockfile (Terraform 1.10+).
# Bucket must be created out-of-band before the first `terraform init`.
# Pass values via -backend-config at init time, e.g.:
#   terraform init \
#     -backend-config="bucket=wactl-tf-state-${AWS_ACCOUNT_ID}" \
#     -backend-config="region=us-east-1"
terraform {
  backend "s3" {
    key            = "wactl/terraform.tfstate"
    use_lockfile   = true
    encrypt        = true
  }
}
