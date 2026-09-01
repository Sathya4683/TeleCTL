# Local backend — state lives in `infra/terraform.tfstate`.
# Pros: zero AWS setup before first `terraform init`; no extra S3 bill.
# Cons: state is on this machine; lose it and you re-apply from scratch.
# Switch back to S3 by adding a `backend "s3" { ... }` block if you
# ever collaborate.
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
